// Suggests a playback speed from a passage's grade level. The recording is never regenerated.
export const SPEED_OPTIONS = [0.5, 0.75, 1, 1.25, 1.5, 2];

// Keys are ReadWorks' grade IDs (canonical_grade), as named in the "Grades" filter on
// readworks.org/find-content. Speeds are the team's choice, informed by students' median
// oral reading rates (Hasbrouck & Tindal). High school isn't listed: 1× is fine there.
const GRADES = {
  16: { question: 'Are you in kindergarten?', speed: 0.5 },
  17: { question: 'Are you in 1st grade?', speed: 0.5 },
  18: { question: 'Are you in 2nd grade?', speed: 0.5 },
  19: { question: 'Are you in 3rd grade?', speed: 0.5 },
  20: { question: 'Are you in 4th grade?', speed: 0.5 },
  21: { question: 'Are you in 5th grade?', speed: 0.75 },
  22: { question: 'Are you in 6th grade?', speed: 0.75 },
  323: { question: 'Are you in 7th grade?', speed: 0.75 },
  343: { question: 'Are you in 8th grade?', speed: 0.75 },
};

// Returns null when this grade has no suggestion.
export const suggestSpeed = gradeId => GRADES[gradeId] ?? null;

// Generated manifests don't carry a grade, so existing audio needn't be regenerated to get one.
// Returns null on any failure: a missing suggestion must never affect reading or listening.
export async function loadGradeId(passage, fetcher = (...args) => fetch(...args)) {
  if (passage?.gradeId != null) return passage.gradeId;
  if (!passage?.source?.uuid) return null;
  try {
    const response = await fetcher(`/api/passages/${encodeURIComponent(passage.source.uuid)}`);
    return response.ok ? (await response.json()).gradeId ?? null : null;
  } catch { return null; }
}
