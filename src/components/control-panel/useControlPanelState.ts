import { safeGetItem, safeGetJSON } from '../../utilis/storage';
import { debugLog } from '../../utilis/debug';

export const readClimbingTime = (): string => {
  const raw = safeGetItem('climbingTime');
  if (!raw) return '05:00';
  try {
    const value = safeGetJSON('climbingTime');
    if (typeof value === 'string') return value;
  } catch (err) {
    debugLog('[readClimbingTime] Failed to parse JSON, using fallback regex:', err);
  }
  const match = raw.match(/^"?(\d{1,2}):(\d{2})"?$/);
  if (match) {
    const mm = match[1].padStart(2, '0');
    const ss = match[2];
    return `${mm}:${ss}`;
  }
  return raw;
};

export const parseTimeCriterionValue = (raw: string | null): boolean | null => {
  if (raw === 'on') return true;
  if (raw === 'off') return false;
  if (!raw) return null;
  try {
    const parsed = safeGetJSON('timeCriterionEnabled');
    return !!parsed;
  } catch {
    return null;
  }
};

export const readTimeCriterionEnabled = (boxId: number): boolean => {
  const perBox = parseTimeCriterionValue(safeGetItem(`timeCriterionEnabled-${boxId}`));
  if (perBox !== null) return perBox;
  const legacy = parseTimeCriterionValue(safeGetItem('timeCriterionEnabled'));
  return legacy ?? false;
};
