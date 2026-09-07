# The demo recording

`demo.py` is the script behind the demo in the README: BUG-LOG-01 fails about one login in three at
random, and a snapshot plus a seed turns it into a case that replays exactly.

It is a real client. It launches an `android-driver` server, calls the same tools an agent calls, and
prints what they return — so anyone can run it and get the same thing, which is the claim the
recording makes.

## Run it

Needs a booted emulator with FlakyDemo built (`cd test_app && ./gradlew :app:assembleDebug`).

```bash
python docs/demo/demo.py --setup     # install, and save the 'clean' snapshot on the login screen
python docs/demo/demo.py             # the demo itself, about 90 seconds
```

`--setup` reuses a device that is already attached rather than booting one, because choosing GPU
flags for an emulator is the sort of thing you have usually already done.

## Recording it

1. **Arrange the screen.** Terminal on the left, emulator window on the right, both fully visible.
   Crop the emulator to the screen rather than the whole window if your recorder can.
2. **Use a clean shell.** The recording will show your prompt, working directory, and anything else
   on screen. A throwaway profile with a plain prompt avoids editing later.
3. **Record the region** covering both windows, at the display's native resolution.
4. **Run `python docs/demo/demo.py`** and let it finish. Do not narrate over the pauses — they are
   there so the output is readable at 1x.
5. **Stop, and check the take** against the list below before converting anything.

### What makes a take usable

- Act 1 actually flaked. If five attempts all passed, run it again — the point of act 1 is a failure
  nobody chose. Do not edit one in.
- The phone's login footer reads `seed 24` during the two failing runs and `seed 20` during the
  passing one. That frame is the proof the demo rests on.
- Both seed-24 runs failed and the seed-20 run passed.
- No credentials, tokens, or unrelated windows anywhere in frame.

### Converting

Trim first, then two passes for a GIF that is not enormous:

```bash
ffmpeg -i take.mov -ss 00:00:04 -to 00:00:29 -c copy demo-trimmed.mov

ffmpeg -i demo-trimmed.mov \
  -vf "fps=12,scale=1200:-1:flags=lanczos,palettegen=stats_mode=diff" -y /tmp/palette.png

ffmpeg -i demo-trimmed.mov -i /tmp/palette.png \
  -lavfi "fps=12,scale=1200:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=3" \
  -y docs/assets/demo.gif
```

Aim for **under 5 MB**. If it comes out larger, drop to `fps=10` or `scale=1000` before shortening
the demo — losing act 1 costs more than losing a few pixels.

For the release page or anywhere that renders video, keep the trimmed `.mov` or export an `.mp4`:
GitHub renders uploaded video there, and it will look considerably better than the GIF.

## Honesty

Caption it as driven by this script. It is not a Claude Code session, and a reader who assumes it is
will feel misled when they see the real thing. The closing frame names the prompt that does the same
work — `/android-driver:repro BUG-LOG-01` — which is the honest bridge between the two.
