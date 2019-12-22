# sync-tube.py

A Python 3 script to sync your YouTube playlist to a local folder

## How it works?

```
usage: sync-tube.py [-h] --playlist PLAYLIST --dest DEST [--keep] [--threshold THRESHOLD]
                    [--processes PROCESSES] [--dont-update] [--verbose]

sync-tube.py - Sync YouTube playlists to your disc using youtube-dl

required arguments:
  --playlist PLAYLIST   playlist to be synced, youtube playlist id
  --dest DEST           destination folder to sync the playlist to

optional arguments:
  --keep                keep files in dest folder that aren't in the playlist
  --threshold THRESHOLD
                        threshold distance for the string metric, if this distance is
                        surpassed two strings are considered different. Default 5
  --processes PROCESSES
                        number of processes to use when downloading. Default is cpu_count *
                        2 i.e. 16
  --dont-update         don't actually change files, just print changes that would be made
  --verbose             be verbose
```

To sync a playlist like `https://www.youtube.com/playlist?list=PLGuwvd-8KqjYGiJ1ota5WVf7u0np0V2-G` to your folder `~/Music` you would then do
`./sync-tube.py --playlist PLGuwvd-8KqjYGiJ1ota5WVf7u0np0V2-G --dest ~/Music`, in this way sync-tube will download all files that are in the remote playlist,
but are not in your local folder and delete all files in your folder that are no lenger in playlist.

You can specify the `--keep` flag if you want to keep files that have been removed from playlist, like if I want to sync two playlists to the same folder I would do
`./sync-tube.py --playlist PLAYLISTA --dest FOLDER --keep` and `./sync-tube.py --playlist PLAYLISTB --dest FOLDER --keep`.

sync-tube works by comparing video titles and filenames using the Levenshtein distance between strings. You may be able to change a little filenames without
breaking sync-tube if you play around with the `--threshold` value, but I would not reccomend it.

## Installation

It's a single script, I would suggest installing dependencies in a Python virtualenv and running the script from there.
You have to generate a YouTube Data API key from the Google Developer Console copy the file `.env.dist` into `.env` and paste your key there.
