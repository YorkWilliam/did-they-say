from flask import Flask, render_template, request, jsonify, Response
import json
import os
import time
from datetime import timedelta

class Cache:
    def __init__(self):
        self.cache_dir = 'cache'
        self.channels_dir = 'cache/channels'
        self.videos_dir = 'cache/videos'
        os.makedirs(self.cache_dir, exist_ok=True)
        os.makedirs(self.channels_dir, exist_ok=True)
        os.makedirs(self.videos_dir, exist_ok=True)
    
    def get_channel_path(self, handle):
        return os.path.join(self.channels_dir, f'{handle}.json')
    
    def get_video_path(self, video_id):
        return os.path.join(self.videos_dir, f'{video_id}.json')

    # channel: handle, channel_id, videos
    def get_channel_cache(self, handle):
        cache_path = self.get_channel_path(handle)
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                return cache_data
            except:
                return None
    def save_channel_cache(self, handle, cache_data):
        cache_path = self.get_channel_path(handle)
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
    
    # video: video_id, channel, title, published_at, transcript
    def get_video_cache(self, video_id):
        cache_path = self.get_video_path(video_id)
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                return cache_data
            except:
                return None
    def save_video_cache(self, video_id, cache_data):
        cache_path = self.get_video_path(video_id)
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)

class BaseSearcher:
    def __init__(self):
        self.language_codes = ['en', 'en-GB', 'en-US']
        self.cache = Cache()
    
    # each instance of BaseSearcher should implement these methods
    # def search_channel(self, handle)
    # def search_video(self, handle, video_id)

    def generate_results(self, handle, term):
        if not handle.startswith('@'):
            handle = '@' + handle

        if not handle or not term:
            yield json.dumps({
                'type': 'error',
                'error': 'Please provide both channel handle and search term'
            }) + '\n'
            return

        channel = self.cache.get_channel_cache(handle)
        if not channel:
            try:
                channel = self.search_channel(handle)
                self.cache.save_channel_cache(handle, channel)
            except Exception as e:
                yield json.dumps({
                    'type': 'error',
                    'error': f'Channel not found: {str(e)}'
                }) + '\n'
                return
        
        videos_processed = 0
        matches_found = 0
        for video_id in channel['video_list']:
            video = self.cache.get_video_cache(video_id)
            if not video:
                try:
                    video = self.search_video(handle, video_id)
                    self.cache.save_video_cache(video_id, video)
                except Exception as e:
                    yield json.dumps({
                        'type': 'error',
                        'error': f'Video not found: {str(e)}'
                    }) + '\n'
                    continue
            if not video:
                continue
            videos_processed += 1

            # search term in transcript
            matches = []
            for line in video['transcript']:
                if term.lower() in line['text'].lower():
                    matches.append({
                        'text': line['text'],
                        'timestamp': line['start'],
                        'timestamp_formatted': self._format_timestamp(line['start'])
                    })
            if matches:
                matches_found += 1
                result = {
                    'title': video['title'],
                    'video_id': video['video_id'],
                    'published_at': video['published_at'],
                    'matches': matches
                }
                yield json.dumps({
                    'type': 'match',
                    'data': result
                }) + '\n'
            
            yield json.dumps({
                'type': 'progress',
                'videos_processed': videos_processed,
                'matches_found': matches_found
            }) + '\n'
                    
    def _format_timestamp(self, seconds):
        return str(timedelta(seconds=int(seconds))).split('.')[0].zfill(8) 