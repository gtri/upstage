# Helper functions for processing state data
import pandas as pd
from datetime import datetime, timedelta

def to_changes(data: list[tuple[datetime, str]], excess=10.0) -> list[tuple[str, datetime, datetime]]:
    start_stop_data = []
    for i in range(len(data) - 1):
        start_time, start_value = data[i]
        end_time, _ = data[i + 1]
        start_stop_data.append((start_value, start_time, end_time))
    start_stop_data.append((data[-1][1], data[-1][0], data[-1][0] + timedelta(minutes=excess)))
    return start_stop_data


def to_step(data: list[tuple[float, float | int]], last_time=None) -> list[tuple[float, float | int]]:
    """Return data as (time, value) pairs that accounts for step-like nature of DES data."""
    step_data = []
    for i in range(len(data) - 1):
        start_time, start_value = data[i]
        end_time, end_value = data[i + 1]
        step_data.append((start_time, start_value))
        if start_value != end_value:
            step_data.append((end_time, start_value))
    # Add the last data point
    step_data.append(data[-1])
    if last_time is not None:
        step_data.append((last_time, step_data[-1][-1]))
    return step_data


def doing_to_gantt(df: pd.DataFrame, actor: str, state: str) -> pd.DataFrame:
    use =  df[(df["Entity Name"] == actor) & (df["State Name"]==state)].sort_values("Time")
    the_data = [(row["Time"], row["Value"]) for _, row in use.iterrows()]
    formatted_data = to_changes(the_data)
    _times = [
        dict(TaskNum=f"Task {i}", Start=start, Finish=finish, Task=value)
        for i, (value, start, finish) in enumerate(formatted_data)
    ]
    return pd.DataFrame(_times)
