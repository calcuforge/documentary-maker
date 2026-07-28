# assets/

Shared BGM tracks, fonts, and other media reusable across explainer-video-maker projects. This directory is for **project-wide** shared assets only — per-video assets live under `projects/{project}/videos/{video}/assets/`.

## BGM tracks

Drop looping BGM mp3 files here, then reference them in `project_prefs.yaml`:

```yaml
bgm:
  volume: 0.12
  track: ../assets/perfect-beauty.mp3   # relative to project dir
  loop: true
```

Or use an absolute path. The `bgm.track` field accepts any resolvable filesystem path.

## Future

- Sound effects library (per-shot `sfx` cue support is planned but not yet implemented).
- Shared Lottie animation JSONs for `LottieAnimation` component (currently each video brings its own under `videos/{v}/animations/`).
