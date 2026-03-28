const HOLD_PRECISION = 10;
const HOLD_EPSILON = 1e-6;

const normalizeHoldValue = (value: number): number => {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return 0;
  }

  const rounded = Math.round(value * HOLD_PRECISION) / HOLD_PRECISION;
  const nearestInteger = Math.round(rounded);
  if (Math.abs(rounded - nearestInteger) < HOLD_EPSILON) {
    return nearestInteger;
  }

  return rounded;
};

export const clampHoldValue = (value: number, max = Number.POSITIVE_INFINITY): number => {
  const normalizedValue = normalizeHoldValue(value);
  const normalizedMax = Number.isFinite(max)
    ? Math.max(0, normalizeHoldValue(max))
    : Number.POSITIVE_INFINITY;

  return normalizeHoldValue(Math.max(0, Math.min(normalizedMax, normalizedValue)));
};

export const applyHoldDelta = (
  previous: number,
  delta = 1,
  max = Number.POSITIVE_INFINITY,
): number => {
  const current = clampHoldValue(previous, max);
  const normalizedDelta = normalizeHoldValue(delta);

  if (normalizedDelta === 1 && !Number.isInteger(current)) {
    return clampHoldValue(Math.floor(current) + 1, max);
  }

  return clampHoldValue(current + normalizedDelta, max);
};

export const formatHoldDisplay = (value: number): string => {
  const normalized = clampHoldValue(value);
  if (Number.isInteger(normalized)) {
    return String(normalized);
  }

  return `${Math.floor(normalized)}+`;
};

export const getHoldProgressRatio = (current: number, holds: number): number => {
  const max = clampHoldValue(holds);
  if (max <= 0) {
    return 0;
  }

  return clampHoldValue(current, max) / max;
};
