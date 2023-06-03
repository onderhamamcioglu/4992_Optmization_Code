import json
import boto3
from boto3.dynamodb.types import TypeDeserializer
import decimal
from ortools.sat.python import cp_model


class DecimalEncoder(json.JSONEncoder):  # DynamoDB Data to JSON
    def default(self, o):
        if isinstance(o, decimal.Decimal):
            return str(o)
        return super(DecimalEncoder, self).default(o)


################################################################################ GET VARIABLES JSON FROM DYNAMODB


def lambda_handler(event, context):
    request_body = json.loads(event['body'])
    head_nurse = request_body['headNurse']

    # Create a DynamoDB client
    dynamodb = boto3.client('dynamodb')

    # Retrieve data from DynamoDB
    response = dynamodb.get_item(
        TableName='variables',
        Key={
            'headNurse': {'S': head_nurse}
        }
    )

    # Check if the item exists in the response
    if 'Item' not in response:
        return {
            'statusCode': 404,
            'body': 'Item not found'
        }

    # Deserialize DynamoDB response
    deserializer = boto3.dynamodb.types.TypeDeserializer()
    item = response['Item']
    deserialized_item = {}

    for key, value in item.items():
        deserialized_item[key] = deserializer.deserialize(value)

    # Convert data to JSON using custom encoder
    input = json.dumps(deserialized_item, cls=DecimalEncoder)

    ############################################################################ Create Schedule

    json_input = json.loads(input)

    head_nurse = json_input['headNurse']
    hospital_name = json_input['hospitalName']
    dept_name = json_input['deptName']
    num_shifts = int(json_input['num_of_shifts'])
    nurses = json_input['names']
    num_days = int(json_input['num_of_shift_days'])
    demand = [int(json_input['demand']['Morning']), int(json_input['demand']['Evening']),
              int(json_input['demand']['Night'])]
    max_consecutive_nights = int(json_input['max_consecutive_nights'])
    min_working_hours = int(json_input['min_working_hours'])
    max_working_hours = int(json_input['max_working_hours'])
    max_subsequent_working_days = int(json_input['max_subsequent_working_days'])
    min_weekend_off_days = int(json_input['min_weekend_off_days'])
    min_night_shifts = int(json_input['min_night_shifts'])
    max_night_shifts = int(json_input['max_night_shifts'])
    min_days_off = int(json_input['min_days_off'])

    # Generate some variables according to inputs
    num_nurses = len(nurses)
    if (num_shifts == 3):
        shifts = ["Morning", "Evening", "Night"]
        shift_hours = [8, 8, 8]
    if (num_shifts == 2):
        shifts = ["Morning", "Night"]
        shift_hours = [12, 12]

    days = []
    for i in range(1, num_days + 1):
        days.append(str(i))
    # -------------------------------------------

    # Opt. Code

    model = cp_model.CpModel()
    # decision variables
    shifts_per_nurse_per_day = {}
    for nurse in range(num_nurses):
        for day in range(num_days):
            for shift in range(num_shifts):
                shifts_per_nurse_per_day[(nurse, day, shift)] = model.NewBoolVar(f"shift_{nurse}_{day}_{shift}")

    # variables for working hours thingy
    total_working_hours = {}
    for nurse in range(num_nurses):
        for day in range(num_days):
            for shift in range(num_shifts):
                total_working_hours[(nurse, day, shift)] = model.NewIntVar(0, shift_hours[shift],
                                                                           f"total_working_hours_{nurse}_{day}_{shift}")

    total_working_hours_flat = [total_working_hours[(nurse, day, shift)] for nurse in range(num_nurses) for day in
                                range(num_days) for shift in range(num_shifts)]
    total_working_hours_sum = model.NewIntVar(min_working_hours, max_working_hours, "total_working_hours_sum")
    model.Add(sum(total_working_hours_flat) == total_working_hours_sum)

    # Maximum number of subsequent working days allowed for a nurse

    for nurse in range(num_nurses):
        for day in range(num_days - max_subsequent_working_days + 1):
            working_days = [
                shifts_per_nurse_per_day[(nurse, day + i, 0)] + shifts_per_nurse_per_day[(nurse, day + i, 1)] +
                shifts_per_nurse_per_day[(nurse, day + i, 2)]
                for i in range(max_subsequent_working_days)]
            model.Add(sum(working_days) <= max_subsequent_working_days)

    # Minimum and maximum number of night shifts per scheduling period

    for nurse in range(num_nurses):
        num_night_shifts = sum(shifts_per_nurse_per_day[(nurse, day, 2)] for day in range(num_days))
        model.Add(num_night_shifts >= min_night_shifts)
        model.Add(num_night_shifts <= max_night_shifts)

    # Total working hours constraint
    total_working_hours = {}

    for nurse in range(num_nurses):
        for day in range(num_days):
            daily_working_hours = [shift_hours[shift] * shifts_per_nurse_per_day[(nurse, day, shift)] for shift in
                                   range(num_shifts)]
            total_working_hours[(nurse, day)] = model.NewIntVar(0, max(shift_hours),
                                                                f"total_working_hours_{nurse}_{day}")
            model.Add(total_working_hours[(nurse, day)] == sum(daily_working_hours))

    # a nurse works at most one shift each day
    for nurse in range(num_nurses):
        for day in range(num_days):
            model.Add(sum(shifts_per_nurse_per_day[(nurse, day, shift)] for shift in range(num_shifts)) <= 1)

    # no morning shift for a nurse after a night shift
    for nurse in range(num_nurses):
        for day in range(num_days - 1):
            night_shift = shifts_per_nurse_per_day[(nurse, day, 2)]
            morning_shift = shifts_per_nurse_per_day[(nurse, day + 1, 0)]
            model.Add(night_shift + morning_shift <= 1)

    # each nurse takes a day off
    for nurse in range(num_nurses):
        for day in range(num_days):
            off_shift = shifts_per_nurse_per_day[(nurse, day, 0)]
            model.Add(
                off_shift + shifts_per_nurse_per_day[(nurse, day, 1)] + shifts_per_nurse_per_day[(nurse, day, 2)] <= 1)

    # demand for nurses for each shift each day is met
    for day in range(num_days):
        for shift in range(num_shifts):
            shift_demand = demand[shift]
            model.Add(sum(shifts_per_nurse_per_day[(nurse, day, shift)] for nurse in range(num_nurses)) >= shift_demand)

    # max number of consecutive night shifts
    for nurse in range(num_nurses):
        for day in range(num_days - max_consecutive_nights):
            consecutive_night_shifts = [shifts_per_nurse_per_day[(nurse, day + i, 2)] for i in
                                        range(max_consecutive_nights)]
            model.Add(sum(consecutive_night_shifts) <= max_consecutive_nights)

    # İki tatil günü arasında iş günü olmaması
    for nurse in range(num_nurses):
        for day in range(1, num_days - 1):
            first_day = shifts_per_nurse_per_day[(nurse, day - 1, 0)]
            second_day = shifts_per_nurse_per_day[(nurse, day + 1, 0)]
            working_day = shifts_per_nurse_per_day[(nurse, day, 0)] + shifts_per_nurse_per_day[(nurse, day, 1)] + \
                          shifts_per_nurse_per_day[(nurse, day, 2)]
            model.Add((first_day + second_day - 1) <= working_day)

    # İki iş günü arasında tatil olmaması
    for nurse in range(num_nurses):
        for day in range(1, num_days - 1):
            work_first = shifts_per_nurse_per_day[(nurse, day - 1, 0)] + shifts_per_nurse_per_day[
                (nurse, day - 1, 1)] + shifts_per_nurse_per_day[(nurse, day - 1, 2)]
            work_second = shifts_per_nurse_per_day[(nurse, day + 1, 0)] + shifts_per_nurse_per_day[
                (nurse, day + 1, 1)] + \
                          shifts_per_nurse_per_day[(nurse, day + 1, 2)]

            off_day = 1 - (shifts_per_nurse_per_day[(nurse, day, 0)] + shifts_per_nurse_per_day[(nurse, day, 1)] +
                           shifts_per_nurse_per_day[(nurse, day, 2)])

            model.Add((work_first + work_second - 1) >= off_day)

    # hafta sonu tatili
    for nurse in range(num_nurses):
        weekend_shifts = []
        for day in [5, 6]:  # 5 = Saturday, 6 = Sunday
            for shift in range(num_shifts):
                weekend_shifts.append(shifts_per_nurse_per_day[(nurse, day, shift)])
        model.Add(sum(weekend_shifts) <= num_shifts * 2 - min_weekend_off_days)

    # En az x tatil günü
    for nurse in range(num_nurses):
        total_shifts = []
        for day in range(num_days):
            for shift in range(num_shifts):
                total_shifts.append(shifts_per_nurse_per_day[(nurse, day, shift)])
        model.Add(sum(total_shifts) <= num_days * num_shifts - min_days_off)

    solver = cp_model.CpSolver()
    status = solver.Solve(model)
    # -------------------------------------------

    # Export as JSON
    if status == cp_model.OPTIMAL:
        result = {
            "headNurse": f"{head_nurse}",
            "hospitalName": f"{hospital_name}",
            "deptName": f"{dept_name}",
            "isFound": True,
            "num_of_shifts": f"{num_shifts}",
            "nurses": []
        }
        for nurse in range(num_nurses):
            nurse_data = {
                "name": f"{nurses[nurse]}",
                "shifts": {
                    "Morning": [],
                    "Evening": [],
                    "Night": []
                }
            }
            for day in range(num_days):
                for shift in range(num_shifts):
                    if solver.Value(shifts_per_nurse_per_day[(nurse, day, shift)]) == 1:
                        shift_name = shifts[shift]
                        day_name = days[day]
                        nurse_data["shifts"][shift_name].append((day + 1))
                        # print(f"Nurse {nurse} works {shifts[shift]} on {days[day]}")
            result["nurses"].append(nurse_data)
    else:
        print("no solution!")
        result = {
            "headNurse": f"{head_nurse}",
            "deptName": f"{dept_name}",
            "isFound": False,
            "nurses": []
        }

    json_result = json.dumps(result, indent=4)

    ################################################################################ Return Schedule

    return {
        'statusCode': 200,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'DELETE,GET,HEAD,OPTIONS,PATCH,POST,PUT'
        },
        'body': json_result
    }