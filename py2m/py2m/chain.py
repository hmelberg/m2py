"""
chain.py — flatten Python method chains into a list of steps.

A chain like:
    df.groupby(['a', 'b'])['income'].transform('mean')
decomposes to:
    root  = Name('df')
    steps = [
        MethodStep('groupby', args=[List(...)], kwargs={}),
        SubscriptStep(key=Constant('income')),
        MethodStep('transform', args=[Constant('mean')], kwargs={}),
    ]

This makes pattern matching trivial: instead of navigating deeply nested
inside-out AST trees, recognisers just scan a flat list.

Bonus: prefix steps that precede groupby (e.g. df[cond].groupby(...)) are
automatically represented as extra steps at the front — no special-casing needed.
"""
import ast
from dataclasses import dataclass, field
from typing import Optional, Any


# ── step types ────────────────────────────────────────────────────────────────

@dataclass
class MethodStep:
    """A method call: .method(*args, **kwargs)"""
    name: str
    args: list = field(default_factory=list)   # list of AST nodes
    kwargs: dict = field(default_factory=dict)  # str → AST node


@dataclass
class SubscriptStep:
    """A subscript access: [key]  — key is an AST node."""
    key: Any


@dataclass
class AttrStep:
    """An attribute access without a call: .attr"""
    name: str


# ── decomposer ────────────────────────────────────────────────────────────────

def decompose(node) -> tuple:
    """
    Flatten a method chain into (root_node, [step, ...]).

    Steps are returned in left-to-right order (root first, outermost last).
    For non-chain nodes (e.g. a bare Name or Constant) the step list is empty.

    Examples
    --------
    df.groupby(g)[col].transform(s)
        → root=Name('df'), steps=[MethodStep('groupby'), SubscriptStep, MethodStep('transform')]

    df['col'].str.lower()
        → root=Name('df'), steps=[SubscriptStep('col'), AttrStep('str'), MethodStep('lower')]

    df[cond].groupby(g)['y'].mean().reset_index()
        → root=Name('df'), steps=[SubscriptStep(cond), MethodStep('groupby'),
                                   SubscriptStep('y'), MethodStep('mean'),
                                   MethodStep('reset_index')]
    """
    steps = []
    current = node

    while True:
        if isinstance(current, ast.Call):
            func = current.func
            if isinstance(func, ast.Attribute):
                # Filter out **kwargs spread (kw.arg is None) — they can't be
                # reliably represented in a simple dict and are rare in our domain.
                kwargs = {
                    kw.arg: kw.value
                    for kw in current.keywords
                    if kw.arg is not None
                }
                steps.append(MethodStep(func.attr, list(current.args), kwargs))
                current = func.value
            else:
                # Free function call like np.log(x) or func(x) — stop here.
                break

        elif isinstance(current, ast.Subscript):
            steps.append(SubscriptStep(current.slice))
            current = current.value

        elif isinstance(current, ast.Attribute):
            steps.append(AttrStep(current.attr))
            current = current.value

        else:
            # Name, Constant, Tuple, etc. — this is the chain root.
            break

    steps.reverse()
    return current, steps


# ── lookup helpers ────────────────────────────────────────────────────────────

def find_method(steps: list, name: str, start: int = 0) -> int:
    """Return index of first MethodStep named *name* at or after *start*, or -1."""
    for i in range(start, len(steps)):
        if isinstance(steps[i], MethodStep) and steps[i].name == name:
            return i
    return -1


def find_attr(steps: list, name: str, start: int = 0) -> int:
    """Return index of first AttrStep named *name* at or after *start*, or -1."""
    for i in range(start, len(steps)):
        if isinstance(steps[i], AttrStep) and steps[i].name == name:
            return i
    return -1


def strip_suffix(steps: list, *names: str) -> list:
    """Return a copy of steps with any trailing MethodSteps whose names are in *names* removed."""
    result = list(steps)
    while result and isinstance(result[-1], MethodStep) and result[-1].name in names:
        result.pop()
    return result


# ── value extraction helpers ──────────────────────────────────────────────────

def str_const(node) -> Optional[str]:
    """Return the string value of an AST Constant node, or None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def str_list(node) -> Optional[list]:
    """
    Extract a list of strings from:
      - a single string Constant → ['value']
      - a List or Tuple of string Constants → ['v1', 'v2', ...]
    Returns None if any element is not a string constant.
    """
    s = str_const(node)
    if s is not None:
        return [s]
    if isinstance(node, (ast.List, ast.Tuple)):
        result = []
        for elt in node.elts:
            v = str_const(elt)
            if v is None:
                return None
            result.append(v)
        return result or None
    return None


def is_df_root(root, df_name: str) -> bool:
    """True if the chain root is the main DataFrame variable."""
    return isinstance(root, ast.Name) and root.id == df_name
