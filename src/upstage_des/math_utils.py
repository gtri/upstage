# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

"""This module contains math utility functions to avoid numpy."""

from math import sqrt

VECTOR = list[float] | tuple[float, ...]


def _vector_subtract(vector_a: VECTOR, vector_b: VECTOR) -> list[float]:
    """Subtract equal-sized vectors.

    Args:
        vector_a (list[float]): Left vector
        vector_b (list[float]): Right vector

    Returns:
        list[float]: Subtracted vector
    """
    if not (len(vector_a) == len(vector_b)):
        raise ValueError("Vectors are not the same size")

    ret = [a - b for a, b in zip(vector_a, vector_b)]
    return ret


def _vector_add(vector_a: VECTOR, vector_b: VECTOR) -> list[float]:
    """Add equal-sized vectors.

    Args:
        vector_a (list[float]): Left vector
        vector_b (list[float]): Right vector

    Returns:
        list[float]: Added vector
    """
    if not (len(vector_a) == len(vector_b)):
        raise ValueError("Vectors are not the same size")

    ret = [a + b for a, b in zip(vector_a, vector_b)]
    return ret


def _vector_dot(vector_a: VECTOR, vector_b: VECTOR) -> float:
    """Inner product of two vectors.

    Args:
        vector_a (VECTOR): Left vector
        vector_b (VECTOR): Right vector

    Returns:
        float: inner product
    """
    return sum(a * b for a, b in zip(vector_a, vector_b))


def _vector_norm(arr: VECTOR) -> float:
    """Norm of a vector.

    Args:
        arr (VECTOR): vector

    Returns:
        float: norm
    """
    s = sum(a**2 for a in arr)
    return sqrt(s)


def _roots(a: float, b: float, c: float) -> list[float]:
    """Calculate the roots of a quadratic.

    The form is ax^2 + bx + c = 0.

    Args:
        a (float): Coefficient on the square term
        b (float): Coefficient on the base term
        c (float): Constant

    Returns:
        list[float]: The two roots, empty if not real.
    """
    discriminant = b**2 - 4 * a * c
    if discriminant < 0:
        return []
    root1 = (-b + sqrt(discriminant)) / (2 * a)
    root2 = (-b - sqrt(discriminant)) / (2 * a)
    return [root1, root2]


def _col_mat_mul(col: VECTOR, mat: list[list[float]]) -> list[float]:
    """Do a matrix multiplication of a column against a matrix.

    Does col @ mat

    Args:
        col (VECTOR): The left vector
        mat (list[list[float]]): The matrix

    Returns:
        list[float]: The multiplied result
    """
    if len(col) != len(mat):
        raise ValueError("Number of values in col must equal number of rows in mat")

    result = [sum(x * y for x, y in zip(col, c)) for c in zip(*mat)]

    return result
