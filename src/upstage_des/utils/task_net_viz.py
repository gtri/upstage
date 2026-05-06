# Copyright (C) 2026 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

"""Visualization builders for task networks."""

from upstage_des.task_networks import GUARD_FUNC, TaskNetwork, TaskNetworkFactory


def _guard_label(guard: GUARD_FUNC | None) -> str:
    """Extract a human-readable label from a guard function."""
    if guard is None:
        return ""
    name: str = getattr(guard, "__name__", "")
    if name and name != "<lambda>":
        return name
    qualname: str = getattr(guard, "__qualname__", "")
    if qualname and "<lambda>" not in qualname:
        return qualname
    return "guard"


def _hook_suffix(net: TaskNetwork, task_name: str) -> str:
    """Return a parenthesized hook list, or empty string."""
    cls = net.task_classes.get(task_name)
    if cls is None:
        return ""
    hooks: list[str] = []
    if "on_enter" in cls.__dict__:
        hooks.append("on_enter")
    if "on_exit" in cls.__dict__:
        hooks.append("on_exit")
    if not hooks:
        return ""
    return f"({', '.join(hooks)})"


def to_mermaid(net: TaskNetwork | TaskNetworkFactory, *, legend: bool = True) -> str:
    """Return a Mermaid graph diagram of the task network.

    Renders in Jupyter, GitHub Markdown, and any Mermaid-compatible viewer.
    Tasks with ``on_enter`` or ``on_exit`` hooks are annotated.

    Args:
        net (TaskNetwork | TaskNetworkFactory): The network to visualize
        legend: Show a legend distinguishing solid (transition) and
            dashed (allowed/queue) edges.  Defaults to True; only
            rendered when dashed edges are present.

    Returns:
        str: Mermaid diagram source.
    """
    if isinstance(net, TaskNetworkFactory):
        net = net.make_network()
    has_allowed = False
    lines = ["graph TD"]
    # Declare every task node so rendering is consistent whether or not
    # a task defines on_enter/on_exit hooks.
    for task_name in net.task_classes:
        node_id = task_name.replace(" ", "_")
        suffix = _hook_suffix(net, task_name)
        if suffix:
            lines.append(f'    {node_id}["{task_name}<br/><sub><i>{suffix}</i></sub>"]')
        else:
            lines.append(f'    {node_id}["{task_name}"]')
    # Edges
    for src, links in net.task_links.items():
        src_id = src.replace(" ", "_")
        transitions = links.transitions
        trans_targets = {tr.target for tr in transitions}
        for tr in transitions:
            label = tr.label if tr.label is not None else _guard_label(tr.guard)
            tgt_id = tr.target.__name__ if isinstance(tr.target, type) else tr.target
            tgt_id = tgt_id.replace(" ", "_")
            if label:
                lines.append(f"    {src_id} -->|{label}| {tgt_id}")
            else:
                lines.append(f"    {src_id} --> {tgt_id}")
        if links.default is not None:
            assert isinstance(links.default, str)
            def_id = links.default.replace(" ", "_")
            if links.default not in trans_targets:
                lines.append(f"    {src_id} --> {def_id}")
        for a in links.allowed:
            assert isinstance(a, str)
            a_id = a.replace(" ", "_")
            if a not in trans_targets and a != links.default:
                has_allowed = True
                lines.append(f"    {src_id} -.-> {a_id}")
    # Legend
    if legend and has_allowed:
        lines.append("")
        lines.append("    subgraph Legend[ ]")
        lines.append("        direction LR")
        lines.append("        L1[ ] -->|transition| L2[ ]")
        lines.append("        L3[ ] -.->|via queue| L4[ ]")
        lines.append("    end")
        lines.append("    style Legend fill:none,stroke:#ccc")
        lines.append("    style L1 fill:none,stroke:none,width:0px")
        lines.append("    style L2 fill:none,stroke:none,width:0px")
        lines.append("    style L3 fill:none,stroke:none,width:0px")
        lines.append("    style L4 fill:none,stroke:none,width:0px")
    return "\n".join(lines)


def to_dot(net: TaskNetwork | TaskNetworkFactory) -> str:
    """Return a Graphviz DOT diagram of the task network.

    Tasks with ``on_enter`` or ``on_exit`` hooks are annotated.

    Args:
        net (TaskNetwork | TaskNetworkFactory): The network to visualize

    Returns:
        str: DOT source string.
    """
    if isinstance(net, TaskNetworkFactory):
        net = net.make_network()
    lines = [
        f"digraph {net.name.replace(' ', '_')} {{",
        "    rankdir=TB;",
        '    node [shape=box, style=rounded, fontname="Helvetica"];',
        '    edge [fontname="Helvetica", fontsize=10];',
        "",
    ]
    # Declare every task node so rendering is consistent whether or not
    # a task defines on_enter/on_exit hooks.
    for task_name in net.task_classes:
        suffix = _hook_suffix(net, task_name)
        if suffix:
            lines.append(
                f'    "{task_name}" [label=<{task_name}<br/>'
                f'<font point-size="10"><i>{suffix}</i></font>>];'
            )
        else:
            lines.append(f'    "{task_name}";')
    lines.append("")
    # Edges
    for src, links in net.task_links.items():
        transitions = links.transitions
        trans_targets = {tr.target for tr in transitions}
        for tr in transitions:
            label = tr.label if tr.label is not None else _guard_label(tr.guard)
            if label:
                lines.append(f'    "{src}" -> "{tr.target}" [label="{label}"];')
            else:
                lines.append(f'    "{src}" -> "{tr.target}";')
        if links.default is not None:
            assert isinstance(links.default, str)
            if links.default not in trans_targets:
                lines.append(f'    "{src}" -> "{links.default}";')
        for a in links.allowed:
            assert isinstance(a, str)
            if a not in trans_targets and a != links.default:
                lines.append(f'    "{src}" -> "{a}" [style=dashed];')
    lines.append("}")
    return "\n".join(lines)
