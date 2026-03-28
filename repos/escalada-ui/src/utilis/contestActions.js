import { debugError } from './debug';
import { safeSetItem, safeGetItem } from './storage';
import { postCmd, getStateSnapshot, requestAdminJson } from './commandClient';

const getBoxVersion = (boxId) => {
  const raw = safeGetItem(`boxVersion-${boxId}`);
  const parsed = raw ? parseInt(raw, 10) : null;
  return Number.isNaN(parsed) ? undefined : parsed;
};

const getSessionId = (boxId) => safeGetItem(`sessionId-${boxId}`);

const setSessionId = (boxId, sessionId) => {
  if (sessionId) safeSetItem(`sessionId-${boxId}`, sessionId);
};

const withBoxMeta = (boxId, payload = {}, includeVersion = true) => ({
  boxId,
  ...payload,
  sessionId: getSessionId(boxId),
  ...(includeVersion ? { boxVersion: getBoxVersion(boxId) } : {}),
});

const persistTimerCmd = (type, boxId) => {
  try {
    safeSetItem('timer-cmd', JSON.stringify({ type, boxId, ts: Date.now() }));
  } catch (err) {
    debugError(`Failed to persist ${type} command`, err);
  }
};

const sendBoxCommand = async (boxId, type, payload = {}, options = {}) => {
  const { includeVersion = true } = options;
  return postCmd(
    withBoxMeta(
      boxId,
      {
        type,
        ...payload,
      },
      includeVersion,
    ),
    type,
  );
};

export async function startTimer(boxId) {
  persistTimerCmd('START_TIMER', boxId);
  return sendBoxCommand(boxId, 'START_TIMER');
}

export async function stopTimer(boxId) {
  persistTimerCmd('STOP_TIMER', boxId);
  return sendBoxCommand(boxId, 'STOP_TIMER');
}

export async function resumeTimer(boxId) {
  persistTimerCmd('RESUME_TIMER', boxId);
  return sendBoxCommand(boxId, 'RESUME_TIMER');
}

export async function updateProgress(boxId, delta = 1) {
  return sendBoxCommand(boxId, 'PROGRESS_UPDATE', { delta });
}

export async function getCompetitionOfficials() {
  return requestAdminJson('/competition_officials', 'GET', 'GET_COMPETITION_OFFICIALS');
}

export async function setCompetitionOfficials(
  judgeChief,
  competitionDirector,
  chiefRoutesetter,
  federalOfficial,
) {
  return requestAdminJson('/competition_officials', 'POST', 'SET_COMPETITION_OFFICIALS', {
    federalOfficial: federalOfficial ?? '',
    judgeChief: judgeChief ?? '',
    competitionDirector: competitionDirector ?? '',
    chiefRoutesetter: chiefRoutesetter ?? '',
  });
}

export async function requestActiveCompetitor(boxId) {
  return sendBoxCommand(boxId, 'REQUEST_ACTIVE_COMPETITOR');
}

export async function submitScore(boxId, score, competitor, registeredTime) {
  return sendBoxCommand(boxId, 'SUBMIT_SCORE', {
    score,
    competitor,
    registeredTime: typeof registeredTime === 'number' ? registeredTime : undefined,
  });
}

export async function modifyScore(boxId, score, competitor, registeredTime) {
  return sendBoxCommand(boxId, 'MODIFY_SCORE', {
    score,
    competitor,
    registeredTime: typeof registeredTime === 'number' ? registeredTime : undefined,
  });
}

export async function registerTime(boxId, registeredTime) {
  return sendBoxCommand(boxId, 'REGISTER_TIME', { registeredTime });
}

export async function initRoute(
  boxId,
  routeIndex,
  holdsCount,
  competitors,
  timerPreset,
  routesCount,
  holdsCounts,
  categorie,
) {
  return postCmd(
    {
      boxId,
      type: 'INIT_ROUTE',
      routeIndex,
      holdsCount,
      routesCount,
      holdsCounts,
      competitors,
      timerPreset,
      categorie,
    },
    'INIT_ROUTE',
  );
}

export async function setTimerPreset(boxId, timerPreset) {
  const fetchAndStoreState = async () => {
    const st = await getStateSnapshot(boxId);
    if (st?.sessionId) setSessionId(boxId, st.sessionId);
    if (typeof st?.boxVersion === 'number') {
      safeSetItem(`boxVersion-${boxId}`, String(st.boxVersion));
    }
    return st;
  };

  let sessionId = getSessionId(boxId);
  let boxVersion = getBoxVersion(boxId);

  if (!sessionId) {
    const st = await fetchAndStoreState();
    sessionId = st?.sessionId;
    boxVersion = typeof st?.boxVersion === 'number' ? st.boxVersion : undefined;
  }

  const doPost = () =>
    postCmd(
      {
        boxId,
        type: 'SET_TIMER_PRESET',
        timerPreset,
        sessionId,
        boxVersion,
      },
      'SET_TIMER_PRESET',
    );

  let result = await doPost();
  if (
    result?.status === 'ignored' &&
    (result.reason === 'stale_version' || result.reason === 'stale_session')
  ) {
    await fetchAndStoreState();
    sessionId = getSessionId(boxId);
    boxVersion = getBoxVersion(boxId);
    result = await doPost();
  }
  return result;
}

export async function requestState(boxId) {
  return postCmd(
    {
      boxId,
      type: 'REQUEST_STATE',
      sessionId: getSessionId(boxId),
    },
    'REQUEST_STATE',
  );
}

export async function resetBox(boxId) {
  return sendBoxCommand(boxId, 'RESET_BOX', {}, { includeVersion: false });
}

export async function resetBoxPartial(boxId, opts = {}) {
  const { resetTimer = false, clearProgress = false, unmarkAll = false } = opts || {};
  return sendBoxCommand(boxId, 'RESET_PARTIAL', {
    resetTimer,
    clearProgress,
    unmarkAll,
  });
}

export async function setTimeTiebreakDecision(boxId, decision, fingerprint) {
  const normalizedDecision = String(decision || '').trim().toLowerCase();
  const normalizedFingerprint = String(fingerprint || '').trim();
  return sendBoxCommand(boxId, 'SET_TIME_TIEBREAK_DECISION', {
    timeTiebreakDecision: normalizedDecision,
    timeTiebreakFingerprint: normalizedFingerprint,
  });
}

export async function setPrevRoundsTiebreakDecision(
  boxId,
  decision,
  fingerprint,
  lineageKey = null,
  order = [],
  ranksByName = {},
) {
  const normalizedDecision = String(decision || '').trim().toLowerCase();
  const normalizedFingerprint = String(fingerprint || '').trim();
  const normalizedLineageKey =
    typeof lineageKey === 'string' && lineageKey.trim() ? lineageKey.trim() : null;
  const normalizedOrder = Array.isArray(order)
    ? order
        .map((item) => (typeof item === 'string' ? item.trim() : ''))
        .filter((item, idx, arr) => item && arr.indexOf(item) === idx)
    : [];
  const normalizedRanksByName =
    ranksByName && typeof ranksByName === 'object'
      ? Object.entries(ranksByName).reduce((acc, [name, rank]) => {
          const cleanName = typeof name === 'string' ? name.trim() : '';
          if (!cleanName) return acc;
          const value = Number(rank);
          if (!Number.isFinite(value) || value <= 0) return acc;
          acc[cleanName] = Math.trunc(value);
          return acc;
        }, {})
      : {};

  return sendBoxCommand(boxId, 'SET_PREV_ROUNDS_TIEBREAK_DECISION', {
    prevRoundsTiebreakDecision: normalizedDecision,
    prevRoundsTiebreakFingerprint: normalizedFingerprint,
    prevRoundsTiebreakLineageKey: normalizedLineageKey,
    prevRoundsTiebreakOrder: normalizedOrder,
    prevRoundsTiebreakRanksByName: normalizedRanksByName,
  });
}

export { getSessionId, setSessionId, getBoxVersion };
