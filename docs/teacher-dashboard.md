# Teacher dashboard demo

Open `/?view=teacher`, or choose **Assign** on a passage. Select a reading, choose With audio or Without audio, select students, optionally set a due date, and create the assignment. Add student names with the roster field. Assignment cards provide a reading link, Copy link, and Remove.

This hackathon version stores the roster and assignments in this browser's local storage. It has four sample students initially. It does not send notifications, create student accounts, sync assignments across devices, or track reading completion. Share the link directly with the intended students. No student names are included in links.

Links carry `audio=on` or `audio=off`. Text-only links do not load audio into the player and hide the audio console, word replay, highlighting switch, and audio details. Text size and font controls remain available. The setting stays in the URL when switching passages. It is a presentation preference, not an authorization boundary: a student can change the URL or open the ordinary reader.

For a production classroom, connect an authenticated teacher/student roster and persistent assignments through the API, and resolve assignment support from server-side permissions rather than trusting URL parameters.

Validation: browser checks covered assigning with and without audio, adding a student, assignment persistence after reload, and text-only mode with no audio source or play button. The reader production build and existing reader tests also pass.
