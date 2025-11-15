"""Solvers for manufacturing setup."""
from collections import defaultdict
from itertools import chain, product
from math import ceil

import networkx as nx
import numpy as np
from inputs import ManufacturingItemData, ManufacturingProcessData, ManufacturingStationData
from scipy.optimize import Bounds, LinearConstraint, milp


def solve_for_inputs(
    outputs: list[ManufacturingItemData],
    processes: list[ManufacturingProcessData],
) -> tuple[dict[str, int], dict[str, int]]:
    """Given outputs, solve for inputs needed, number of processes.

    Args:
        outputs (list[ManufacturingItemData]): Desired outputs
        processes (list[ManufacturingProcessData]): Processes

    Returns:
        tuple[dict[str, int], dict[str, int]]:
            Counts of processes needed, counts of resources needed
    """
    needs = defaultdict(int)
    needs.update(**{o.name: o.amount for o in outputs})
    process_counts = defaultdict(int)

    G = nx.DiGraph()
    for proc in processes:
        inputs = proc["inputs"].keys()
        outputs = proc["outputs"].keys()
        for a, b in product(inputs, outputs):
            G.add_edge(b, a)

    for node in nx.topological_sort(G):
        amt = needs[node]
        proc = [p for p in processes if node in p["outputs"]]
        if not proc:
            continue
        assert len(proc) == 1
        proc = proc[0]
        amt_per = proc["outputs"][node]
        runs = ceil(amt / amt_per)
        process_counts[proc["name"]] += runs
        for inp, num in proc["inputs"].items():
            needs[inp] += num * runs

    return process_counts, needs


def assign_work(
    process_counts: dict[str, int],
    machines: list[ManufacturingStationData],
    machine_classes: list[str],
) -> tuple[dict[str, list[str]] | None, str]:
    """Assign processes to machines.

    We've pre-solved the counts of processes to avoid a large optimization problem.

    This is an ILP formulation that minimizes the deviation of number of jobs
    over each machine class. We're using that as a proxy for shortest time
    because that's not worth the time to set up for example sims.

    We're also not going to do any special ordering of processes. Yet.

    But having the ILP built here might mean I update it in the future for fun.

    Args:
        process_counts (dict[str, int]): _description_
        machines (list[ManufacturingStationData]): _description_
        machine_classes (list[str]): Partial names to match on.

    Returns:
        dict[str, list[str]] | None: Machine name to process list or None if error.
        str: Error message, if error
    """
    mach_names = [x.name for x in machines]
    processes = list(process_counts.keys())

    # Make data based on index
    mach_to_proc_map = {
        i: [processes.index(p) for p in m.capable_processes]
        for i, m in enumerate(machines)
    }
    proc_count_map = {
        processes.index(k): v
        for k, v in process_counts.items()
    }
    mach_to_class_map = {
        i: [j for j, c in enumerate(machine_classes) if c in m][0]
        for i, m in enumerate(mach_names)
    }

    # create variable information/indices
    M = len(machines)
    C = len(machine_classes)

    var_info = []
    x_idx = {}
    l_idx = {}
    u_idx = {}

    idx = 0
    # Set variables for machines to number of each process
    for m in range(M):
        for p in mach_to_proc_map[m]:
            var_info.append(('x', m, p))
            x_idx[(m, p)] = idx
            idx += 1

    # Variables to track number of jobs per machine class
    for c in range(C):
        var_info.append(('L', c, None))
        l_idx[c] = idx
        idx += 1
        var_info.append(('U', c, None))
        u_idx[c] = idx
        idx += 1

    n_vars = len(var_info)

    # objective building
    c_obj = np.zeros(n_vars)
    for c in range(C):
        # we sum over Upper - Lower
        c_obj[u_idx[c]] = 1.0
        c_obj[l_idx[c]] = -1.0

    # Integrality and bounds of the variables
    integrality = np.ones(n_vars, dtype=bool)
    bounds = Bounds(lb=0, ub=sum(process_counts.values()))

    constraints = []

    # We must do the right number of each process
    for p, count in proc_count_map.items():
        row = np.zeros(n_vars)
        for m, ps in mach_to_proc_map.items():
            if p in ps:
                row[x_idx[(m, p)]] = 1.0
        con = LinearConstraint(A=row, lb=count, ub=count)
        constraints.append(con)

    # Build the constraints that count processes per machine per class
    for c in range(C):
        for m, mc in mach_to_class_map.items():
            if mc != c:
                continue
            # lower bound
            row_l = np.zeros(n_vars)
            for p in mach_to_proc_map[m]:
                row_l[x_idx[(m, p)]] = 1.0
            row_l[l_idx[c]] = -1.0
            con_l = LinearConstraint(A=row_l, lb=0, ub=np.inf)
            constraints.append(con_l)

            # upper bound
            row_u = np.zeros(n_vars)
            for p in mach_to_proc_map[m]:
                row_u[x_idx[(m, p)]] = 1.0
            row_u[u_idx[c]] = -1.0
            con_u = LinearConstraint(A=row_u, lb=-np.inf, ub=0)
            constraints.append(con_u)

    res = milp(
        c=c_obj,
        constraints=constraints,
        integrality=integrality,
        bounds=bounds
    )
    if not res.success:
        return None, res.message
    
    results: dict[str, list[str]] = defaultdict(list)
    
    for (m, p), idx in x_idx.items():
        mname = mach_names[m]
        pname = processes[p]
        results[mname].append(pname)
    return results, ""
