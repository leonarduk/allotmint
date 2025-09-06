# Architecture

## Persistence

State that needs to survive page reloads can be stored either in the URL or in
`localStorage`.

Use URL query parameters when the state should be shareable or bookmarkable and
forms part of navigation. Prefer `localStorage` for purely client-side
preferences or state that would clutter the URL. Access `localStorage` via the
helpers in `src/utils/storage.ts`, which automatically handle JSON encoding.
