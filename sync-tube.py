#!/usr/bin/env python3

from argparse import ArgumentParser
from colored import fg, attr
from glob import glob
import Levenshtein
from math import inf
from multiprocessing import cpu_count, Pool
from os import access, chdir, getcwd, unlink, W_OK
from os.path import basename, isfile, join
from youtube_dl import YoutubeDL, DownloadError, downloader

INFO = f'[{fg("green")}{attr("bold")}+{attr("reset")}]'
ERROR = f'[{fg("red")}{attr("bold")}-{attr("reset")}]'

ISSUE_LINK = 'https://github.com/ekardnam/sync-tube.py/issues'

THRESHOLD = 5
PROCESSES = cpu_count() * 2
QUALITY = 192

def get_local_playlist_files(directory):
    for file in glob(join(directory, "*.mp3")):
        if isfile(file):
            yield basename(file)

def get_remote_playlist_videos(playlist):
    with YoutubeDL({'ignoreerrors': True, 'quiet': True}) as ydl:
        playlist_info = ydl.extract_info(playlist, download=False)
        return playlist_info['entries']

def strip_extension(filename):
    return '.'.join(filename.split('.')[:-1])

def string_similarity_metric(string1, string2):
    return Levenshtein.distance(string1, string2)

def best_distance_title_match_in_list(str, str_list):
    record = inf
    record_str = ''
    for string in str_list:
        distance = string_similarity_metric(str, string)
        if distance < record:
            record = distance
            record_str = string
    return (record, record_str)

def string_in_list(string, str_list, threshold):
    return best_distance_title_match_in_list(string, str_list)[0] <= threshold

def get_videos_to_download(local_filenames, remote_videos, threshold):
    return list(filter(lambda video: not string_in_list(video['title'], local_filenames, threshold), remote_videos))

def get_files_to_delete(local_files, remote_videos, threshold):
    remote_video_titles = list(map(lambda v: v['title'], remote_videos))
    return list(filter(lambda file: not string_in_list(strip_extension(file), remote_video_titles, threshold), local_files))

def get_video_url_from_id(id):
    return f'https://www.youtube.com/watch?v={id}'

def youtube_dl_hook(d):
        if d['status'] == 'finished':
            print(f'{INFO} Finished downloading {strip_extension(d["filename"])}')

class YoutubeDLLogger(object):
    def __init__(self, verbose):
        self.verbose = verbose

    def debug(self, msg):
        if self.verbose:
            print(msg)

    def warning(self, msg):
        print(msg)

    def error(self, msg):
        print(msg)

class YoutubeDLDownloaderPool(object):
    def __init__(self, processes, options):
        self.processes = processes
        self.options = options

    def download_video(self, video):
        with YoutubeDL(self.options) as ydl:
            try:
                ydl.download([video])
            except DownloadError as e:
                print(e.exc_info)
                print(f'{ERROR} An Exception as occured. Try updating YouTubeDL. If this happen again please report it at {ISSUE_LINK}')
                exit()

    def download(self, videos):
        with Pool(processes=self.processes) as pool:
            pool.map(self.download_video, videos)

def main(playlist, dest, keep, processes, threshold, dont_update, thumbnail, quality, verbose):
    ydl_options = {
        'outtmpl': '%(title)s.%(ext)s',
        'format': 'bestaudio/best',
        'logger': YoutubeDLLogger(verbose),
        'progress_hooks': [youtube_dl_hook],
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3'
        }]
    }

    if not access(dest, W_OK):
        print(f'{ERROR} Cannot write to playlist directory. Aborting')
        return

    ydl_options['postprocessors'][0]['preferredquality'] = str(quality)

    #Embed video thumnail as coverart
    if thumbnail:
        ydl_options['writethumbnail'] = True
        ydl_options['postprocessors'].append({'key': 'EmbedThumbnail'})
        ydl_options['postprocessors'].append({'key': 'FFmpegMetadata'})

    downloader = YoutubeDLDownloaderPool(processes, ydl_options)

    print(f'{INFO} Getting local playlist information', end='', flush=True)
    local_files = list(get_local_playlist_files(dest))
    local_files_stripped = list(map(strip_extension, local_files))
    print('. Done')
    if verbose:
        print(f'{INFO} Files in local playlist {dest}:')
        print(' - \t{}'.format('\n - \t'.join(local_files_stripped)))

    print(f'{INFO} Pulling remote playlist information', end='', flush=True)
    remote_videos = get_remote_playlist_videos(playlist)
    print('. Done')
    if verbose:
        print(f'{INFO} Videos in remote playlist {playlist}:')
        print(' - \t{}'.format('\n - \t'.join(map(lambda v: v['title'], remote_videos))))

    videos_to_download = get_videos_to_download(local_files_stripped, remote_videos, threshold)

    if videos_to_download:
        print(f'{INFO} Have to download: ')
        print(' - \t{}'.format('\n - \t'.join(map(lambda v: v['title'], videos_to_download))))
        if not dont_update:
            cwd = getcwd()
            chdir(dest)
            urls = list(map(lambda video: get_video_url_from_id(video['id']), videos_to_download))
            print(urls)
            downloader.download(urls)
            chdir(cwd)
        else:
            print('Not downloading. To download drop the --dont-update flag')
    else:
        print(f'{INFO} Nothing new to download')

    files_to_delete = get_files_to_delete(local_files, remote_videos, threshold)
    if files_to_delete:
        print(f'{INFO} These files are no longer in remote playlist: ')
        print(' - \t{}'.format('\n - \t'.join(files_to_delete)))

        if not keep and not dont_update:
            print(f'{INFO} Deleting them')
            for path in map(lambda filename: join(dest, filename), files_to_delete):
                try:
                    unlink(path)
                except FileNotFoundError:
                    print(f'{INFO} File not found. Did sombody delete file before me?')
        else:
            print(f'{INFO} To delete them don\'t use the --keep or the --dont-update option')
    else:
        print(f'{INFO} All files are still in remote playlist')

if __name__ == '__main__':
    parser = ArgumentParser(description='sync-tube.py - Sync YouTube playlists to your disc using youtube-dl')
    parser._action_groups.pop()
    required_named_args = parser.add_argument_group('required arguments')
    required_named_args.add_argument('--playlist', help='playlist to be synced, youtube playlist id', required=True)
    required_named_args.add_argument('--dest', help='destination folder to sync the playlist to', required=True)
    optional_named_args = parser.add_argument_group('optional arguments')
    optional_named_args.add_argument('--keep', default=False, action='store_true', help='keep files in dest folder that aren\'t in the playlist')
    optional_named_args.add_argument('--threshold', type=int, default=THRESHOLD, help=f'threshold distance for the string metric, if this distance is surpassed two strings are considered different. Default {THRESHOLD}')
    optional_named_args.add_argument('--processes', type=int, default=PROCESSES, help=f'number of processes to use when downloading. Default is cpu_count * 2 i.e. {PROCESSES}')
    optional_named_args.add_argument('--dont-update', default=False, action='store_true', help='don\'t actually change files, just print changes that would be made')
    optional_named_args.add_argument('--thumbnail', default=False, action='store_true', help='embeds video thumbnail as coverart')
    optional_named_args.add_argument('--quality', type=int, default=QUALITY, help=f'Mp3 Quality in bitrate. Default {QUALITY} kbps')
    optional_named_args.add_argument('--verbose', default=False, action='store_true', help='be verbose')
    args = parser.parse_args()
    main(args.playlist, args.dest, args.keep, args.processes, args.threshold, args.dont_update, args.thumbnail, args.quality, args.verbose)
