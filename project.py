import os
import time
import redis
import psycopg2
import imagehash
from PIL import Image
from functools import partial
from multiprocessing import Pool
from pymongo import MongoClient
from configurations import *

RESULT = []


def postgres_connection():
    connection = psycopg2.connect(user=POSTGRES_USER, password=POSTGRES_PASSWORD,
                                  host=POSTGRES_HOST, port=POSTGRES_PORT, database=POSTGRES_DATABASE)
    return connection


def mongo_connection():
    client = MongoClient(MONGO_URL)
    return client


def redis_connection():
    redis_client = redis.Redis()
    return redis_client


def redis_data_insertion():
    r_con = redis_connection()
    r_con.flushdb()
    r_con.mset({'30fps': 30, '60fps': 60})


def mongo_data_insertion():
    m_con = mongo_connection()
    r_con = redis_connection()
    db = m_con['test']
    fps = int(r_con.get('30fps').decode('utf-8'))

    ads = db['ads_data']
    ads.drop()
    ads_dir = os.listdir(PATH_ADS)
    print(len(ads_dir))
    for d in ads_dir:
        chunks = d.split('_')
        adv_name = chunks[0]
        ad_name = chunks[1]
        duration = round(len(os.listdir(os.path.join(PATH_ADS+d))) / fps, 2)
        ads_list = os.listdir(os.path.join(PATH_ADS+d))

        ads.insert_one({'advertiser_name': adv_name, 'ad_name': ad_name,
                        'duration': duration, 'filepath': os.path.join(PATH_ADS+d+'/'+ads_list[0])})

    print('Ads data inserted successfully..')


def postgres_insertion(frames, detected_time):
    p_con = postgres_connection()
    m_con = mongo_connection()
    r_con = redis_connection()

    db = m_con['test']
    data = []
    for d in db['ads_data'].find():
        data.append(d)
    cursor = p_con.cursor()

    table_drop = 'DROP TABLE IF EXISTS adc_data'
    table_create = ''' CREATE TABLE adc_data
    (ADVERTISER_NAME TEXT NOT NULL,
    AD_NAME TEXT NOT NULL,
    AD_FRAME TEXT NOT NULL,
    RECOGNITION_TIME REAL NOT NULL,
    DURATION REAL NOT NULL,
    FPS INT NOT NULL,
    STREAM_FRAME TEXT NOT NULL);
    '''
    cursor.execute(table_drop)
    cursor.execute(table_create)
    fps = int(r_con.get('30fps').decode('utf-8'))
    cnt = 0
    for i in range(len(frames)):
        stream_frame = frames[i].split('/')[-1].split('.')[0]
        recog_time = detected_time[i]
        for j in data:
            print(j['filepath'])
            if stream_frame in j['filepath']:
                adv_name = j['advertiser_name']
                ad_name = j['ad_name']
                duration = j['duration']
                ad_frame = j['filepath'].split('/')[-1].split('.')[0]
                print(
                    f'{adv_name}, {ad_name}, {ad_frame}, {recog_time}, {duration}, {fps}, {stream_frame}')
                table_insert = "INSERT INTO adc_data(ADVERTISER_NAME, AD_NAME, AD_FRAME, RECOGNITION_TIME, DURATION, FPS, STREAM_FRAME) VALUES(%s, %s, %s, %s, %s, %s, %s);"
                cursor.execute(table_insert, (adv_name, ad_name,
                                              ad_frame, recog_time, duration, fps, stream_frame))
                print('entry in postgres...')
                break
    p_con.commit()
    print('Data entered in postgres successfully')


def getHash(path):
    img = Image.open(path)
    return imagehash.dhash(img), path


def get_ad_frames_hashes():
    ads_dir = os.listdir(PATH_ADS)
    fframes = []
    for d in ads_dir:
        ads = os.listdir(os.path.join(PATH_ADS+d))
        fframes.append(os.path.join(PATH_ADS + d + '/' + ads[0]))
    ad_hashes = {}
    for i in fframes:
        ad_hashes[imagehash.dhash(Image.open(i))] = i
    return ad_hashes


def driver():
    r_con = redis_connection()

    ads_hashes = get_ad_frames_hashes()
    spath = []

    stream = os.listdir(PATH_STREAM)
    for d in stream:
        spath.append(os.path.join(PATH_STREAM+d))

    first = int(spath[0].split('/')[-1].split('.')[0])
    fps = int(r_con.get('30fps').decode('utf-8'))

    stream_frames = []
    detected_time = []

    pool = Pool(10)
    for h, name in pool.imap(getHash, spath):
        if h in ads_hashes:
            print('frame found')
            detected = int(name.split('/')[-1].split('.')[0])
            detected_time.append(round((detected - first) / fps, 2))
            stream_frames.append(name)
            ads_hashes.pop(h)

    print('\n')
    postgres_insertion(stream_frames, detected_time)


if __name__ == '__main__':
    redis_data_insertion()
    mongo_data_insertion()
    driver()
