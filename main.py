from ortools.sat.python import cp_model 

model = cp_model.CpModel()

# //TODO JSON INPUT AND PARAMETERS, NURSE NAMES CAN BE MATCHED WITH IDS?

# indices
num_nurses = int(input("Number of working nurses: ")) #number of available nurses //TODO len(nurses[])
num_shifts = 3  #number of shifts in a day

shifts = ["Morning", "Evening", "Night"] #names of shifts

shift_hours = [8, 8, 8] #how many hours does a shift last //TODO = (24 / len(shifts[]))

days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"] #literally just names of days in a week
num_days = len(days) #a week 

demand = {"Morning": 2,"Evening": 3,"Night": 4} #how many nurses do we need in a shift

max_consecutive_nights = 4 #max consecutive night shifts that a nurse can work

# minimum and maximum number of working hours per month
min_working_hours = 120
max_working_hours = 200

# maximum number of subsequent working days allowed for a nurse
max_subsequent_working_days = 5

# minimum number of off days on weekends
min_weekend_off_days = 2

# maximum number of inexperienced nurses in a shift
max_inexperienced_nurses = 3

# minimum and maximum number of night shifts per scheduling period
min_night_shifts = 4
max_night_shifts = 6

# a nurse should have 4 days off every scheduling period
min_days_off = 4


########################################################################################################################


# decision variables
shifts_per_nurse_per_day = {}
for nurse in range(num_nurses):
    for day in range(num_days):
        for shift in range(num_shifts):
            shifts_per_nurse_per_day[(nurse, day, shift)] = model.NewBoolVar(f"shift_{nurse}_{day}_{shift}")

# constraints

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
        model.Add(off_shift + shifts_per_nurse_per_day[(nurse, day, 1)] + shifts_per_nurse_per_day[(nurse, day, 2)] <= 1)

# demand for nurses for each shift each day is met
for day in range(num_days):
    for shift in range(num_shifts):
        shift_demand = demand[shifts[shift]]
        model.Add(sum(shifts_per_nurse_per_day[(nurse, day, shift)] for nurse in range(num_nurses)) >= shift_demand)

# max number of consecutive night shifts
for nurse in range(num_nurses):
    for day in range(num_days - max_consecutive_nights):
        consecutive_night_shifts = [shifts_per_nurse_per_day[(nurse, day+i, 2)] for i in range(max_consecutive_nights)]
        model.Add(sum(consecutive_night_shifts) <= max_consecutive_nights)


solver = cp_model.CpSolver()
status = solver.Solve(model)


########################################################################################################################


#OUTPUT //TODO ADD JSON OUTPUT


if status == cp_model.OPTIMAL:
    for nurse in range(num_nurses):
        for day in range(num_days):
            for shift in range(num_shifts):
                if solver.Value(shifts_per_nurse_per_day[(nurse, day, shift)]) == 1:
                    print(f"Nurse {nurse+1} works {shifts[shift]} on {days[day]}")
else:
    print("a feasible solution is sadly not possible")