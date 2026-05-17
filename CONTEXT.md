# Escalada Competition

Escalada Competition describes a live lead-climbing event where categories run on one or more parallel judging stations and produce rankings for competitors, officials, judges, and spectators.

## Language

**Competition**:
The event being operated from setup through live judging, public display, ranking, export, and recovery.
_Avoid_: tournament, meet

**Category**:
A named group of competitors that is run and ranked together.
_Avoid_: box name, listbox name

**Box**:
A judging station that runs one category at a time.
_Avoid_: lane, screen, device

**Route**:
One climb within a category, identified by a 1-based route number and a fixed number of holds.
_Avoid_: problem, stage

**Competitor**:
A climber entered in a category, optionally associated with a club.
_Avoid_: athlete, participant

**Hold Count**:
The competitor's current or submitted progress on a route, including plus progress as a decimal increment.
_Avoid_: points, score value

**Top**:
A completed route, reached when the submitted hold count reaches the route's configured hold total.
_Avoid_: max score

**Timer Preset**:
The configured duration available to each competitor attempt.
_Avoid_: climbing time

**Registered Time**:
The recorded time for a competitor's attempt, used only when time-based ranking criteria apply.
_Avoid_: elapsed time, timer value

**Judge Remote**:
The per-box interface used by a judge to control timer, hold progress, time registration, and score submission.
_Avoid_: mobile app, judge page

**Control Panel**:
The admin interface used to configure categories, control boxes, manage security, export results, and monitor audit events.
_Avoid_: dashboard, admin page

**Contest Display**:
The per-box full-screen display for showing the active category, timer, current competitor, next competitor, and progress.
_Avoid_: viewer page, TV page

**Public View**:
The unauthenticated spectator-facing experience for live rankings, live climbing, and competition officials.
_Avoid_: public site, landing page

**Competition Official**:
A named official role attached to the whole competition, such as federal official, chief judge, competition director, or chief routesetter.
_Avoid_: staff, admin user

**Previous-Rounds Tiebreak**:
A ranking decision that uses prior route or round ordering to split tied competitors.
_Avoid_: manual tiebreak

**Time Tiebreak**:
A ranking decision that uses registered attempt time to split eligible podium ties.
_Avoid_: time criterion

**Admin Unlock**:
The temporary state that permits admin mutation actions after license checks succeed.
_Avoid_: login, auth

**Recovery Override**:
A temporary emergency bypass that can replace the USB license requirement after a one-time recovery code is consumed.
_Avoid_: recovery login, backdoor

## Relationships

- A **Competition** contains one or more **Categories**.
- A **Category** is run on exactly one active **Box** at a time.
- A **Box** runs one **Route** at a time for its active **Category**.
- A **Category** contains one or more **Competitors**.
- A **Route** has exactly one configured maximum **Hold Count**.
- A **Competitor** can have one submitted **Hold Count** and optional **Registered Time** per **Route**.
- A **Control Panel** can operate many **Boxes**.
- A **Judge Remote** operates exactly one **Box**.
- A **Contest Display** shows exactly one **Box**.
- A **Public View** can show rankings across many **Boxes** or live climbing for one **Box**.
- A **Time Tiebreak** can be applied after a **Previous-Rounds Tiebreak** when an eligible tie remains.
- An **Admin Unlock** requires a valid admin license and either a valid USB license or an active **Recovery Override**.

## Example Dialogue

> **Dev:** "When a judge submits a competitor's **Hold Count**, should the next **Competitor** become active on the same **Box**?"
> **Domain expert:** "Yes. The **Judge Remote** submits the result for the current **Route**, the competitor is marked as done, and the next unmarked competitor in that **Category** becomes current."

## Flagged Ambiguities

- "Score" appears in code and UI exports, but the domain term is **Hold Count** for route progress and submitted climb result.
- "Time criterion" appears in code, but the domain term is **Time Tiebreak** when it affects ranking.
- "Athlete" appears in ranking internals, but user-facing product language should use **Competitor**.
