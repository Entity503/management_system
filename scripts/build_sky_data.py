"""把 d3-celestial 的原始星表压缩成前端用的 sky.json。

用法：
    python scripts/build_sky_data.py

输入（scripts/data/，不参与部署）：
    stars.6.json              恒星（mag <= 6，约 5000 颗）
    constellations.lines.json 88 星座连线
    constellations.json       星座名称（含中文）

输出（static/sky/）：
    sky.json                  精简后的数据（约 200 KB）
    sky.json.gz               预压缩版本，供 WhiteNoise 直接返回
"""

import gzip
import json
import math
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(BASE_DIR, 'scripts', 'data')
OUT_DIR = os.path.join(BASE_DIR, 'static', 'sky')

# d3-celestial 的 zh 字段是繁体，这里统一成简体（88 星座标准中文名）
ZH_SIMPLIFIED = {
    'And': '仙女座', 'Ant': '唧筒座', 'Aps': '天燕座', 'Aqr': '宝瓶座', 'Aql': '天鹰座',
    'Ara': '天坛座', 'Ari': '白羊座', 'Aur': '御夫座', 'Boo': '牧夫座', 'Cae': '雕具座',
    'Cam': '鹿豹座', 'Cnc': '巨蟹座', 'CVn': '猎犬座', 'CMa': '大犬座', 'CMi': '小犬座',
    'Cap': '摩羯座', 'Car': '船底座', 'Cas': '仙后座', 'Cen': '半人马座', 'Cep': '仙王座',
    'Cet': '鲸鱼座', 'Cha': '蝘蜓座', 'Cir': '圆规座', 'Col': '天鸽座', 'Com': '后发座',
    'CrA': '南冕座', 'CrB': '北冕座', 'Crv': '乌鸦座', 'Crt': '巨爵座', 'Cru': '南十字座',
    'Cyg': '天鹅座', 'Del': '海豚座', 'Dor': '剑鱼座', 'Dra': '天龙座', 'Equ': '小马座',
    'Eri': '波江座', 'For': '天炉座', 'Gem': '双子座', 'Gru': '天鹤座', 'Her': '武仙座',
    'Hor': '时钟座', 'Hya': '长蛇座', 'Hyi': '水蛇座', 'Ind': '印第安座', 'Lac': '蝎虎座',
    'Leo': '狮子座', 'LMi': '小狮座', 'Lep': '天兔座', 'Lib': '天秤座', 'Lup': '豺狼座',
    'Lyn': '天猫座', 'Lyr': '天琴座', 'Men': '山案座', 'Mic': '显微镜座', 'Mon': '麒麟座',
    'Mus': '苍蝇座', 'Nor': '矩尺座', 'Oct': '南极座', 'Oph': '蛇夫座', 'Ori': '猎户座',
    'Pav': '孔雀座', 'Peg': '飞马座', 'Per': '英仙座', 'Phe': '凤凰座', 'Pic': '绘架座',
    'Psc': '双鱼座', 'PsA': '南鱼座', 'Pup': '船尾座', 'Pyx': '罗盘座', 'Ret': '网罟座',
    'Sge': '天箭座', 'Sgr': '人马座', 'Sco': '天蝎座', 'Scl': '玉夫座', 'Sct': '盾牌座',
    'Ser': '巨蛇座', 'Sex': '六分仪座', 'Tau': '金牛座', 'Tel': '望远镜座', 'Tri': '三角座',
    'TrA': '南三角座', 'Tuc': '杜鹃座', 'UMa': '大熊座', 'UMi': '小熊座', 'Vel': '船帆座',
    'Vir': '室女座', 'Vol': '飞鱼座', 'Vul': '狐狸座',
}


def load(name):
    with open(os.path.join(RAW_DIR, name), encoding='utf-8') as handle:
        return json.load(handle)


def build_names():
    names = {}
    for feature in load('constellations.json')['features']:
        props = feature.get('properties') or {}
        names[feature['id']] = {
            'zh': props.get('zh') or props.get('name') or feature['id'],
            'en': props.get('en') or props.get('name') or '',
            'abbr': props.get('desig') or feature['id'],
            'rank': int(props.get('rank') or 3),
        }
    return names


def load_descriptions():
    """人工撰写的 88 星座科普简介（本地文件，不依赖外部 API）。"""
    path = os.path.join(RAW_DIR, 'constellation_info.json')
    if not os.path.exists(path):
        return {}
    with open(path, encoding='utf-8') as handle:
        return json.load(handle)


def build_stars():
    stars = []
    for feature in load('stars.6.json')['features']:
        props = feature.get('properties') or {}
        magnitude = props.get('mag')
        if magnitude is None:
            continue
        ra, dec = feature['geometry']['coordinates'][:2]
        stars.append([
            round(float(ra), 2),
            round(float(dec), 2),
            round(float(magnitude), 1),
            round(float(props.get('bv') or 0.65), 2),
        ])
    return stars


def build_constellations(names, descriptions):
    constellations = []
    for feature in load('constellations.lines.json')['features']:
        geometry = feature.get('geometry') or {}
        segments = []
        vertices = []
        for line in geometry.get('coordinates') or []:
            for start, end in zip(line, line[1:]):
                segments.append([
                    round(float(start[0]), 2), round(float(start[1]), 2),
                    round(float(end[0]), 2), round(float(end[1]), 2),
                ])
                vertices.append(start)
        if not segments:
            continue

        # 赤经跨 0 度时直接平均会跑偏，用圆周平均
        sin_sum = sum(math.sin(math.radians(v[0])) for v in vertices)
        cos_sum = sum(math.cos(math.radians(v[0])) for v in vertices)
        label_ra = math.degrees(math.atan2(sin_sum, cos_sum)) % 360
        label_dec = sum(v[1] for v in vertices) / len(vertices)

        info = names.get(feature['id'], {})
        extra = descriptions.get(feature['id'], {})
        constellations.append({
            'id': feature['id'],
            'zh': ZH_SIMPLIFIED.get(feature['id']) or info.get('zh') or feature['id'],
            'en': info.get('en') or '',
            'abbr': info.get('abbr') or feature['id'],
            'rank': info.get('rank', 3),
            'label': [round(label_ra, 2), round(label_dec, 2)],
            'desc': extra.get('desc', ''),
            'star': extra.get('star', ''),
            'segments': segments,
        })
    return constellations


def main():
    names = build_names()
    descriptions = load_descriptions()
    constellations = build_constellations(names, descriptions)
    data = {
        'stars': build_stars(),
        'constellations': constellations,
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, 'sky.json')
    with open(out_path, 'w', encoding='utf-8') as handle:
        json.dump(data, handle, ensure_ascii=False, separators=(',', ':'))

    with open(out_path, 'rb') as handle:
        payload = handle.read()
    with open(out_path + '.gz', 'wb') as handle:
        with gzip.GzipFile(fileobj=handle, mode='wb', mtime=0) as gz:
            gz.write(payload)

    print(
        'stars=%d constellations=%d segments=%d desc=%d missing=%s size=%.0fKB gz=%.0fKB'
        % (
            len(data['stars']),
            len(constellations),
            sum(len(item['segments']) for item in constellations),
            sum(1 for item in constellations if item['desc']),
            [item['id'] for item in constellations if not item['desc']],
            len(payload) / 1024,
            os.path.getsize(out_path + '.gz') / 1024,
        )
    )


if __name__ == '__main__':
    main()
