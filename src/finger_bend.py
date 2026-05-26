"""3D finger bend detection helpers.

Provides utilities to compute the joint angle at the PIP joint using 3D
landmark coordinates and decide if a finger is 'bent' using a configurable
angle threshold. Intended for use with MediaPipe normalized landmarks.
"""
from math import acos, degrees


def _vec(a, b):
    """Return vector from point a to b as tuple (x,y,z). Points have .x/.y/.z."""
    return (b.x - a.x, b.y - a.y, b.z - a.z)


def _dot(u, v):
    return u[0]*v[0] + u[1]*v[1] + u[2]*v[2]


def _norm(u):
    return (u[0]*u[0] + u[1]*u[1] + u[2]*u[2]) ** 0.5


def angle_between_vectors_degrees(u, v):
    """Return angle in degrees between vectors u and v, or None if degenerate."""
    nu = _norm(u)
    nv = _norm(v)
    if nu < 1e-8 or nv < 1e-8:
        return None
    cosv = _dot(u, v) / (nu * nv)
    # Clamp numerical jitter
    if cosv > 1.0:
        cosv = 1.0
    elif cosv < -1.0:
        cosv = -1.0
    try:
        return degrees(acos(cosv))
    except Exception:
        return None


def pip_joint_angle_degrees(mcp, pip, tip):
    """Compute the angle (degrees) at the PIP joint using vectors MCP->PIP and PIP->TIP.

    Returns None when vectors are degenerate.
    """
    v1 = _vec(mcp, pip)
    v2 = _vec(pip, tip)
    return angle_between_vectors_degrees(v1, v2)


def is_finger_bent(mcp, pip, tip, threshold_deg=30.0):
    """Return (bool, angle) whether the finger is bent above threshold.

    - threshold_deg: angle above which the finger is considered bent.
    - Returns (True, angle) when bent, (False, angle) when not, (False, None)
      when angle could not be computed.
    """
    ang = pip_joint_angle_degrees(mcp, pip, tip)
    if ang is None:
        return False, None
    return (ang > threshold_deg), ang
