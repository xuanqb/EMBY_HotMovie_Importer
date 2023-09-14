import urllib.parse
from configparser import ConfigParser

import requests
import feedparser
import re

from typing import List

config = ConfigParser()
with open('config.conf', encoding='utf-8') as f:
    config.read_file(f)


class DbMovie:
    def __init__(self, name, year, type):
        self.name = name
        self.year = year
        self.type = type


class DbMovieRss:
    def __init__(self, title, movies: List[DbMovie]):
        self.title = title
        self.movies = movies


class EmbyBox:
    def __init__(self, box_id, box_movies):
        self.box_id = box_id
        self.box_movies = box_movies


class Get_Detail(object):

    def __init__(self):
        self.noexist = []
        self.dbmovies = {}

        # 获取配置项的值
        self.emby_server = config.get('Server', 'emby_server')
        self.emby_api_key = config.get('Server', 'emby_api_key')
        self.rsshub_server = config.get('Server', 'rsshub_server')
        self.rss_ids = config.get('Collection', 'rss_ids').split(',')

        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.54 Safari/537.36 Edg/101.0.1210.39"
        }

    def search_emby_by_name_and_year(self, db_movie: DbMovie):
        name = db_movie.name
        yearParam = f"&Years={db_movie.year}"
        # 删除季信息
        if db_movie.type == "tv":
            yearParam = ''
        url = f"{self.emby_server}/emby/Items?api_key={self.emby_api_key}&Recursive=true&IncludeItemTypes=movie,Series&SearchTerm={name}{yearParam}"
        response = requests.get(url)
        data = response.json()
        if response.status_code == 200 and data.get('TotalRecordCount', 0) > 0:
            return data
        else:
            return None

    def create_collection(self, collection_name, emby_id):
        encoded_collection_name = urllib.parse.quote(collection_name, safe='')
        url = f"{self.emby_server}/emby/Collections?IsLocked=false&Name={encoded_collection_name}&Ids={emby_id}&api_key={self.emby_api_key}"
        headers = {
            "accept": "application/json"
        }
        response = requests.post(url, headers=headers)
        if response.status_code == 200:
            collection_id = response.json().get('Id')
            print(f"成功创建合集: {collection_id}")
            return collection_id
        else:
            print("创建合集失败.")
            return None

    def add_movie_to_collection(self, emby_id, collection_id):
        url = f"{self.emby_server}/emby/Collections/{collection_id}/Items?Ids={emby_id}&api_key={self.emby_api_key}"
        headers = {"accept": "*/*"}
        response = requests.post(url, headers=headers)
        response.raise_for_status()
        return response.status_code == 204

    def check_collection_exists(self, collection_name) -> EmbyBox:
        encoded_collection_name = urllib.parse.quote(collection_name, safe='')
        url = f"{self.emby_server}/Items?IncludeItemTypes=BoxSet&Recursive=true&SearchTerm={encoded_collection_name}&api_key={self.emby_api_key}"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if len(data["Items"]) > 0 and data["Items"][0]["Type"] == "BoxSet":
                emby_box_id = data["Items"][0]['Id']
                return EmbyBox(emby_box_id, self.get_emby_box_movie(emby_box_id))
        return EmbyBox(None, [])

    def get_emby_box_movie(self, box_id):
        url = f"{self.emby_server}/emby/Items?api_key={self.emby_api_key}&ParentId={box_id}"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            return [item["Name"] for item in data["Items"]]
        return []

    def run(self):
        # 获取豆瓣rss
        for rss_id in self.rss_ids:
            self.dbmovies = self.get_douban_rss(rss_id)
            box_name = self.dbmovies.title
            print(f'更新 {box_name} rss_id:{rss_id}')
            # 如果存在返回id，否则返回''
            emby_box = self.check_collection_exists(box_name)
            for db_movie in self.dbmovies.movies:
                box_id = emby_box.box_id
                movie_name = db_movie.name
                if movie_name in emby_box.box_movies:
                    continue
                emby_data = self.search_emby_by_name_and_year(db_movie)
                if movie_name in self.noexist:
                    continue
                elif emby_data and not box_id:
                    emby_id = emby_data["Items"][0]["Id"]
                    box_id = self.create_collection(box_name, emby_id)
                    print(f"影视 '{movie_name}' 加入到合集成功.")
                elif emby_data:
                    emby_id = emby_data["Items"][0]["Id"]
                    added_to_collection = self.add_movie_to_collection(emby_id, box_id)
                    if added_to_collection:
                        print(f"影视 '{movie_name}' 加入到合集成功.")
                    else:
                        print(f"影视 '{movie_name}' 加入到合集内失败.")
                else:
                    self.noexist.append(movie_name)

    def get_douban_rss(self, rss_id):
        # 解析rss
        rss_url = f"{self.rsshub_server}/douban/movie/weekly/{rss_id}"
        # print(f"rss_url: {rss_url}")
        feed = feedparser.parse(rss_url)
        # 封装成对象
        movies = []
        for item in feed.entries:
            name = item.title
            type = item.type
            if type == 'book':
                continue
                # 删除季信息
            if type == "tv":
                name = re.sub(r" 第[一二三四五六七八九十\d]+季", "", name)
            movies.append(DbMovie(name, item.year, type))
        db_movie = DbMovieRss(feed.feed.title, movies)
        return db_movie


if __name__ == "__main__":
    gd = Get_Detail()
    gd.run()
