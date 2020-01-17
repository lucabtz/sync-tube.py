#!/usr/bin/env python3

from argparse import ArgumentParser
from colored import fg, attr
from environs import Env
from glob import glob
import Levenshtein
from math import inf
from multiprocessing import cpu_count, Pool
from os import access, chdir, getcwd, unlink, W_OK
from os.path import basename, isfile, join
from youtube_api import YouTubeDataAPI
from youtube_dl import YoutubeDL
from enum import Enum

INFO = f'[{fg("green")}{attr("bold")}+{attr("reset")}]'
ERROR = f'[{fg("red")}{attr("bold")}-{attr("reset")}]'

THRESHOLD = 5
PROCESSES = cpu_count() * 4
QUALITY = 192

class PostProcessor(Enum):
    EXTRACT_AUDIO = 0
    EMBED_THUMBNAIL = 1
    FFMPEG_METADATA = 2
    def __int__(self):
        return self.value

YOUTUBE_DL_OPTIONS = {
    'outtmpl': '%(title)s.%(ext)s',
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': str(QUALITY),
    }, 
    {}, {}]
}


#
# get_local_playlist_files - yields the files in the local playlist to be synced
# directory - path to the playlist
#
def get_local_playlist_files(directory):
    for file in glob(join(directory, "*.mp3")):
        if isfile(file):
            yield basename(file)

#
# strip_extension - strips a file extension
# example filename.test.txt gets mapped to filename.test
# filename - the filename
#
def strip_extension(filename):
    return '.'.join(filename.split('.')[:-1])


#
# string_similarity_metric - returns how much two strings are similar in the Levenshtein metric
# string1 - one string
# string2 - another string
#
def string_similarity_metric(string1, string2):
    return Levenshtein.distance(string1, string2)

#
# best_distance_title_match_in_list - returns a tuple with distance and best match in the list
# str   - the target string
# str_list - the string list
#
def best_distance_title_match_in_list(str, str_list):
    record = inf
    record_str = ''
    for string in str_list:
        distance = string_similarity_metric(str, string)
        if distance < record:
            record = distance
            record_str = string
    return (record, record_str)

#
# string_in_list - checks if a string is in a list up to a threshold difference
# string    - the string
# str_list  - the list
# threshold - the threshold
#
def string_in_list(string, str_list, threshold):
    return best_distance_title_match_in_list(string, str_list)[0] <= threshold

#
# get_videos_to_download - returns a list of videos to be downloaded
# local_filenames - the local playlist filenames (with stripped extension)
# remote_videos  - a list of the remote playlist videos
# threshold      - the threshold
#
def get_videos_to_download(local_filenames, remote_videos, threshold):
    return list(filter(lambda video: not string_in_list(video['video_title'], local_filenames, threshold), remote_videos))

#
# get_files_to_delete - returns a list of files that are no longer in the remote playlist
# local_files    - a list of the local files in playlist (with extension)
# remote_videos - a list of the remote_playlist videos
# threshold     - the threshold
#
def get_files_to_delete(local_files, remote_videos, threshold):
    remote_video_titles = list(map(lambda v: v['video_title'], remote_videos))
    return list(filter(lambda file: not string_in_list(strip_extension(file), remote_video_titles, threshold), local_files))

#
# get_video_url_from_id - returns the video url from a given video id
# id - video id
#
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

#
# youtube_dl_download - downloads the given video using youtube_dl
# url - video url
#
def youtube_dl_download(url):
    with YoutubeDL(YOUTUBE_DL_OPTIONS) as ydl:
        ydl.download([url])

#
# download_videos_pool - download videos in a process pool
# videos    - the videos to download
# processes - how many processes to use
#
def download_videos_pool(videos, processes, verbose):
    YOUTUBE_DL_OPTIONS['progress_hooks'] = [youtube_dl_hook]
    YOUTUBE_DL_OPTIONS['logger'] = YoutubeDLLogger(verbose)
    with Pool(processes=processes) as pool:
        pool.map(youtube_dl_download, videos)

#
# main
# playlist - playlist id of the playlist to be synced
# dest     - destination folder to sync
# keep     - keep music files that are not in the playlist
# api_key  - youtube api key
#
def main(playlist, dest, keep, api_key, processes, threshold, dont_update, thumbnail, quality, verbose):
    youtube = YouTubeDataAPI(api_key)

    if not access(dest, W_OK):
        print(f'{ERROR} Cannot write to playlist directory. Aborting')
        return

    #Embed video thumnail as coverart
    if thumbnail:
        YOUTUBE_DL_OPTIONS['writethumbnail'] = True
        YOUTUBE_DL_OPTIONS['postprocessors'][int(PostProcessor.EMBED_THUMBNAIL)]['key'] = 'EmbedThumbnail'
        YOUTUBE_DL_OPTIONS['postprocessors'][int(PostProcessor.FFMPEG_METADATA)]['key'] = 'FFmpegMetadata'

    if quality:
        YOUTUBE_DL_OPTIONS['postprocessors'][int(PostProcessor.EXTRACT_AUDIO)]['preferredquality'] = str(quality)

    print(f'{INFO} Getting local playlist information', end='', flush=True)
    local_files = list(get_local_playlist_files(dest))
    local_files_stripped = list(map(strip_extension, local_files))
    print('. Done')
    if verbose:
        print(f'{INFO} Files in local playlist {dest}:')
        print(' - \t{}'.format('\n - \t'.join(local_files_stripped)))

    print(f'{INFO} Pulling remote playlist information', end='', flush=True)
    remote_videos = youtube.get_video_metadata(list(map(lambda v: v['video_id'], youtube.get_videos_from_playlist_id(playlist))))
    print('. Done')
    if verbose:
        print(f'{INFO} Videos in remote playlist {playlist}:')
        print(' - \t{}'.format('\n - \t'.join(map(lambda v: v['video_title'], remote_videos))))

    videos_to_download = get_videos_to_download(local_files_stripped, remote_videos, threshold)

    if videos_to_download:
        print(f'{INFO} Have to download: ')
        print(' - \t{}'.format('\n - \t'.join(map(lambda v: v['video_title'], videos_to_download))))
        if not dont_update:
            cwd = getcwd()
            chdir(dest)
            download_videos_pool(list(map(lambda video: get_video_url_from_id(video['video_id']), videos_to_download)), processes, verbose)
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
    env = Env()
    env.read_env()
    main(args.playlist, args.dest, args.keep, env('YOUTUBE_KEY'), args.processes, args.threshold, args.dont_update, args.thumbnail, args.quality, args.verbose)
