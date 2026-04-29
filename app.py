from flask import Flask, request, jsonify
import urllib.request
import urllib.parse
import json
import re
from datetime import datetime

app = Flask(__name__)

CACHE = {}
CACHE_DURATION = 300

# ============================================================
# UTILITAIRES
# ============================================================

def fetch_url(url, headers=None):
    default_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Referer': 'https://www.tiktok.com/',
    }
    if headers:
        default_headers.update(headers)
    req = urllib.request.Request(url, headers=default_headers)
    with urllib.request.urlopen(req, timeout=15) as response:
        return response.read().decode('utf-8', errors='ignore')

def get_cache(key):
    if key in CACHE:
        data, timestamp = CACHE[key]
        if (datetime.now() - timestamp).total_seconds() < CACHE_DURATION:
            return data
    return None

def set_cache(key, data):
    CACHE[key] = (data, datetime.now())

def detect_niche(bio, nickname):
    text = (bio + ' ' + nickname).lower()
    niches = {
        "beauté": ['beauté', 'beauty', 'makeup', 'skincare', 'cosmét', 'maquillage'],
        "fitness": ['fitness', 'gym', 'workout', 'sport', 'muscle', 'fit'],
        "cuisine": ['cuisine', 'food', 'recette', 'chef', 'cooking', 'recipe'],
        "mode": ['mode', 'fashion', 'style', 'outfit', 'ootd'],
        "voyage": ['voyage', 'travel', 'world', 'tourisme', 'wanderlust'],
        "gaming": ['gamer', 'gaming', 'esport', 'twitch', 'stream'],
        "musique": ['musicien', 'singer', 'artist', 'music', 'rap', 'dj'],
        "comédie": ['humour', 'comedy', 'funny', 'lol', 'meme', 'ridere', 'laugh'],
        "éducation": ['éducation', 'apprend', 'cours', 'tuto', 'learn', 'student'],
        "business": ['entrepreneur', 'business', 'startup', 'ceo', 'founder'],
        "danse": ['dance', 'danse', 'choreo', 'dancer'],
        "tech": ['tech', 'developer', 'code', 'ai', 'crypto'],
        "famille": ['mom', 'dad', 'family', 'maman', 'papa', 'enfant']
    }
    detected = []
    for niche, keywords in niches.items():
        if any(kw in text for kw in keywords):
            detected.append(niche)
    return detected if detected else ["général"]

def calculate_authenticity_score(followers, following, likes, videos):
    score = 100
    raisons = []
    
    if followers > 0 and following > 0:
        ratio = following / followers
        if ratio > 0.5:
            score -= 30
            raisons.append("Ratio abonnements/abonnés suspect")
    
    if videos > 0 and likes > 0 and followers > 0:
        likes_per_video = likes / videos
        engagement = (likes_per_video / followers) * 100 if followers > 0 else 0
        if engagement < 0.5:
            score -= 25
            raisons.append("Engagement très faible vs abonnés")
        elif engagement > 50:
            score -= 15
            raisons.append("Engagement anormalement élevé")
    
    if videos < 5 and followers > 10000:
        score -= 20
        raisons.append("Beaucoup d'abonnés mais peu de vidéos")
    
    if not raisons:
        raisons.append("Profil cohérent et authentique")
    
    return {"score": max(score, 0), "raisons": raisons}


# ============================================================
# RÉCUPÉRATION DES DONNÉES TIKTOK
# ============================================================

def get_tiktok_profile(username):
    cache_key = "profile:" + username
    cached = get_cache(cache_key)
    if cached:
        return cached
    
    username = username.replace('@', '').strip()
    url = "https://www.tiktok.com/@" + username
    html = fetch_url(url)
    
    followers = following = likes = videos = 0
    bio = nickname = avatar = ''
    verified = False
    user_id = sec_uid = ''
    
    sigi_match = re.search(r'<script id="SIGI_STATE"[^>]*>(.*?)</script>', html, re.DOTALL)
    
    if sigi_match:
        try:
            sigi_data = json.loads(sigi_match.group(1))
            users = sigi_data.get('UserModule', {}).get('users', {})
            stats = sigi_data.get('UserModule', {}).get('stats', {})
            
            for key, user in users.items():
                nickname = user.get('nickname', username)
                bio = user.get('signature', '')
                verified = user.get('verified', False)
                avatar = user.get('avatarLarger', '')
                user_id = user.get('id', '')
                sec_uid = user.get('secUid', '')
                break
            
            for key, s in stats.items():
                followers = s.get('followerCount', 0)
                following = s.get('followingCount', 0)
                likes = s.get('heartCount', 0)
                videos = s.get('videoCount', 0)
                break
        except:
            pass
    
    if followers == 0:
        for pattern, var in [
            (r'"followerCount":(\d+)', 'followers'),
            (r'"followingCount":(\d+)', 'following'),
            (r'"heartCount":(\d+)', 'likes'),
            (r'"videoCount":(\d+)', 'videos')
        ]:
            m = re.search(pattern, html)
            if m:
                if var == 'followers': followers = int(m.group(1))
                elif var == 'following': following = int(m.group(1))
                elif var == 'likes': likes = int(m.group(1))
                elif var == 'videos': videos = int(m.group(1))
        
        for pattern, var in [
            (r'"signature":"([^"]*)"', 'bio'),
            (r'"nickname":"([^"]*)"', 'nickname'),
            (r'"avatarLarger":"([^"]*)"', 'avatar')
        ]:
            m = re.search(pattern, html)
            if m:
                if var == 'bio': bio = m.group(1)
                elif var == 'nickname': nickname = m.group(1)
                elif var == 'avatar': avatar = m.group(1).replace('\\u002F', '/')
        
        v = re.search(r'"verified":(true|false)', html)
        if v:
            verified = v.group(1) == 'true'
    
    engagement_rate = round((likes / (followers * videos) * 100), 2) if followers > 0 and videos > 0 else 0
    niches = detect_niche(bio, nickname)
    auth = calculate_authenticity_score(followers, following, likes, videos)
    
    if followers >= 1000000:
        tier = "Mega Influencer"
        score_influence = 100
    elif followers >= 100000:
        tier = "Macro Influencer"
        score_influence = 80
    elif followers >= 10000:
        tier = "Micro Influencer"
        score_influence = 60
    elif followers >= 1000:
        tier = "Nano Influencer"
        score_influence = 40
    else:
        tier = "Creator"
        score_influence = 20
    
    result = {
        "username": username,
        "nickname": nickname,
        "bio": bio,
        "verified": verified,
        "avatar": avatar,
        "url": "https://www.tiktok.com/@" + username,
        "user_id": user_id,
        "sec_uid": sec_uid,
        "statistiques": {
            "abonnes": followers,
            "abonnements": following,
            "likes_total": likes,
            "videos": videos,
            "engagement_rate": engagement_rate
        },
        "influence": {
            "tier": tier,
            "score": score_influence
        },
        "niches": niches,
        "authenticite": auth,
        "timestamp": datetime.now().isoformat()
    }
    
    set_cache(cache_key, result)
    return result


def get_tiktok_videos(username, limit=10):
    username = username.replace('@', '').strip()
    url = "https://www.tiktok.com/@" + username
    html = fetch_url(url)
    
    videos = []
    
    sigi_match = re.search(r'<script id="SIGI_STATE"[^>]*>(.*?)</script>', html, re.DOTALL)
    if sigi_match:
        try:
            sigi_data = json.loads(sigi_match.group(1))
            items = sigi_data.get('ItemModule', {})
            for vid_id, video in list(items.items())[:limit]:
                stats = video.get('stats', {})
                videos.append({
                    "id": vid_id,
                    "description": video.get('desc', ''),
                    "url": "https://www.tiktok.com/@" + username + "/video/" + vid_id,
                    "duree": video.get('video', {}).get('duration', 0),
                    "vues": stats.get('playCount', 0),
                    "likes": stats.get('diggCount', 0),
                    "commentaires": stats.get('commentCount', 0),
                    "partages": stats.get('shareCount', 0),
                    "date": video.get('createTime', 0),
                    "musique": video.get('music', {}).get('title', ''),
                    "hashtags": [t.get('hashtagName') for t in video.get('textExtra', []) if t.get('hashtagName')]
                })
        except:
            pass
    
    return videos


# ============================================================
# ENDPOINTS
# ============================================================

@app.route('/tiktok/profile', methods=['GET'])
def tiktok_profile():
    username = request.args.get('username', '').strip()
    if not username:
        return jsonify({"erreur": "Paramètre username requis"}), 400
    try:
        return jsonify(get_tiktok_profile(username))
    except Exception as e:
        return jsonify({"erreur": "Profil introuvable: " + str(e)}), 404


@app.route('/tiktok/videos', methods=['GET'])
def tiktok_videos():
    username = request.args.get('username', '').strip()
    limit = min(int(request.args.get('limit', 10)), 30)
    if not username:
        return jsonify({"erreur": "Paramètre username requis"}), 400
    try:
        videos = get_tiktok_videos(username, limit)
        total_vues = sum(v.get('vues', 0) for v in videos)
        total_likes = sum(v.get('likes', 0) for v in videos)
        return jsonify({
            "username": username,
            "total_videos": len(videos),
            "stats_globales": {
                "vues_totales": total_vues,
                "likes_total": total_likes,
                "moyenne_vues": round(total_vues / len(videos)) if videos else 0,
                "moyenne_likes": round(total_likes / len(videos)) if videos else 0
            },
            "videos": videos,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"erreur": str(e)}), 404


@app.route('/tiktok/analyze', methods=['GET'])
def tiktok_analyze():
    username = request.args.get('username', '').strip()
    if not username:
        return jsonify({"erreur": "Paramètre username requis"}), 400
    
    try:
        profile = get_tiktok_profile(username)
        videos = get_tiktok_videos(username, 5)
        
        score_collaboration = profile['influence']['score']
        if profile['authenticite']['score'] < 70:
            score_collaboration -= 20
        if profile['statistiques']['engagement_rate'] >= 3:
            score_collaboration += 10
        score_collaboration = max(0, min(100, score_collaboration))
        
        forces = []
        faiblesses = []
        
        if profile['statistiques']['abonnes'] >= 100000:
            forces.append("Audience large (" + str(profile['statistiques']['abonnes']) + " abonnés)")
        if profile['verified']:
            forces.append("Compte vérifié")
        if profile['authenticite']['score'] >= 80:
            forces.append("Profil authentique")
        if profile['statistiques']['engagement_rate'] >= 3:
            forces.append("Excellent taux d'engagement")
        
        if profile['statistiques']['engagement_rate'] < 1:
            faiblesses.append("Taux d'engagement faible")
        if profile['statistiques']['videos'] < 10:
            faiblesses.append("Peu de contenu publié")
        if profile['authenticite']['score'] < 70:
            faiblesses.append("Authenticité douteuse")
        
        return jsonify({
            "username": username,
            "profil": profile,
            "score_collaboration": score_collaboration,
            "recommandation": "RECOMMANDÉ" if score_collaboration >= 70 else "À CONSIDÉRER" if score_collaboration >= 50 else "NON RECOMMANDÉ",
            "forces": forces,
            "faiblesses": faiblesses,
            "dernieres_videos": videos[:5] if videos else [],
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"erreur": str(e)}), 500


@app.route('/tiktok/influencer-roi', methods=['POST'])
def influencer_roi():
    data = request.get_json()
    username = data.get('username', '')
    budget = float(data.get('budget', 1000))
    objectif = data.get('objectif', 'visibilité')
    
    if not username:
        return jsonify({"erreur": "Paramètre username requis"}), 400
    
    try:
        profile = get_tiktok_profile(username)
        followers = profile['statistiques']['abonnes']
        engagement = profile['statistiques']['engagement_rate']
        
        cpm_estime = 5 if followers >= 1000000 else 8 if followers >= 100000 else 12 if followers >= 10000 else 20
        impressions_estimees = (budget / cpm_estime) * 1000
        engagements_estimes = round(impressions_estimees * (engagement / 100))
        
        prix_post_min = followers * 0.01
        prix_post_max = followers * 0.05
        
        if objectif == 'visibilité':
            roi_score = 80 if engagement >= 3 else 60
        elif objectif == 'conversion':
            roi_score = 70 if engagement >= 5 else 50
        else:
            roi_score = 65
        
        return jsonify({
            "influenceur": profile['nickname'],
            "abonnes": followers,
            "budget": budget,
            "objectif": objectif,
            "estimations": {
                "impressions": int(impressions_estimees),
                "engagements": engagements_estimes,
                "cpm_estime": cpm_estime,
                "prix_post_min": round(prix_post_min, 2),
                "prix_post_max": round(prix_post_max, 2)
            },
            "score_roi": roi_score,
            "conseils": [
                "Négociez le prix entre " + str(round(prix_post_min, 2)) + "€ et " + str(round(prix_post_max, 2)) + "€",
                "Demandez les statistiques détaillées avant collaboration",
                "Privilégiez les contenus authentiques alignés avec votre marque"
            ],
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"erreur": str(e)}), 500


@app.route('/tiktok/compare', methods=['GET'])
def tiktok_compare():
    usernames_str = request.args.get('usernames', '')
    if not usernames_str:
        return jsonify({"erreur": "Paramètre usernames requis"}), 400
    usernames = [u.strip().replace('@', '') for u in usernames_str.split(',')][:5]
    
    results = []
    for username in usernames:
        try:
            data = get_tiktok_profile(username)
            results.append({
                "username": username,
                "nickname": data['nickname'],
                "abonnes": data['statistiques']['abonnes'],
                "likes": data['statistiques']['likes_total'],
                "videos": data['statistiques']['videos'],
                "engagement": data['statistiques']['engagement_rate'],
                "tier": data['influence']['tier'],
                "verified": data['verified'],
                "niches": data['niches']
            })
        except:
            pass
    
    results_sorted = sorted(results, key=lambda x: x['abonnes'], reverse=True)
    
    return jsonify({
        "comparaison": results_sorted,
        "leader": results_sorted[0] if results_sorted else None,
        "timestamp": datetime.now().isoformat()
    })


@app.route('/tiktok/hashtag', methods=['GET'])
def tiktok_hashtag():
    hashtag = request.args.get('tag', '').replace('#', '').strip()
    if not hashtag:
        return jsonify({"erreur": "Paramètre tag requis"}), 400
    
    try:
        url = "https://www.tiktok.com/tag/" + urllib.parse.quote(hashtag)
        html = fetch_url(url)
        
        views_match = re.search(r'"viewCount":(\d+)', html)
        videos_match = re.search(r'"videoCount":(\d+)', html)
        
        views = int(views_match.group(1)) if views_match else 0
        videos = int(videos_match.group(1)) if videos_match else 0
        
        if views >= 1000000000:
            popularite = "Viral"
            score = 100
        elif views >= 100000000:
            popularite = "Très populaire"
            score = 80
        elif views >= 10000000:
            popularite = "Populaire"
            score = 60
        elif views >= 1000000:
            popularite = "Émergent"
            score = 40
        else:
            popularite = "Niche"
            score = 20
        
        return jsonify({
            "hashtag": "#" + hashtag,
            "url": url,
            "vues_totales": views,
            "nombre_videos": videos,
            "popularite": popularite,
            "score_potentiel": score,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"erreur": str(e)}), 500


@app.route('/tiktok/trending', methods=['GET'])
def tiktok_trending():
    region = request.args.get('region', 'FR').upper()
    limit = min(int(request.args.get('limit', 10)), 30)
    
    try:
        url = "https://www.tiktok.com/trending?region=" + region
        html = fetch_url(url)
        
        hashtags = list(dict.fromkeys(re.findall(r'"hashtagName":"([^"]+)"', html)))[:limit]
        sounds = list(dict.fromkeys(re.findall(r'"musicName":"([^"]+)"', html)))[:limit]
        
        return jsonify({
            "region": region,
            "hashtags_trending": hashtags,
            "sons_trending": sounds,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"erreur": str(e)}), 500


@app.route('/tiktok/best-time', methods=['GET'])
def best_posting_time():
    niche = request.args.get('niche', 'general').lower()
    region = request.args.get('region', 'FR').upper()
    
    times_by_niche = {
        "beauté": ["19h-21h", "12h-14h"],
        "fitness": ["6h-8h", "17h-19h"],
        "cuisine": ["11h-12h", "18h-20h"],
        "mode": ["20h-22h", "13h-15h"],
        "gaming": ["20h-23h", "16h-18h"],
        "musique": ["19h-22h", "21h-23h"],
        "comédie": ["20h-23h", "12h-14h"],
        "business": ["7h-9h", "17h-19h"],
        "general": ["19h-22h", "12h-14h"]
    }
    
    times = times_by_niche.get(niche, times_by_niche['general'])
    days = ["Mardi", "Jeudi", "Dimanche"]
    
    return jsonify({
        "niche": niche,
        "region": region,
        "meilleurs_creneaux": times,
        "meilleurs_jours": days,
        "timestamp": datetime.now().isoformat()
    })


@app.route('/tiktok/influencer-check', methods=['GET'])
def influencer_check():
    username = request.args.get('username', '').strip()
    niche = request.args.get('niche', '').strip()
    
    if not username:
        return jsonify({"erreur": "Paramètre username requis"}), 400
    
    try:
        data = get_tiktok_profile(username)
        followers = data['statistiques']['abonnes']
        engagement = data['statistiques']['engagement_rate']
        
        score = 0
        criteres = []
        
        if followers >= 10000:
            score += 30
            criteres.append("OK " + str(followers) + " abonnes")
        else:
            criteres.append("KO " + str(followers) + " abonnes (min 10K)")
        
        if engagement >= 3:
            score += 30
            criteres.append("OK Engagement " + str(engagement) + "%")
        elif engagement >= 1:
            score += 15
            criteres.append("WARN Engagement " + str(engagement) + "%")
        else:
            criteres.append("KO Engagement " + str(engagement) + "%")
        
        if data['verified']:
            score += 20
            criteres.append("OK Compte verifie")
        
        if data['authenticite']['score'] >= 70:
            score += 20
            criteres.append("OK Profil authentique")
        else:
            criteres.append("KO Authenticite douteuse")
        
        if score >= 70:
            statut = "INFLUENCEUR QUALIFIE"
        elif score >= 40:
            statut = "INFLUENCEUR POTENTIEL"
        else:
            statut = "PAS ENCORE INFLUENCEUR"
        
        return jsonify({
            "username": username,
            "niche": niche,
            "statut": statut,
            "score": score,
            "criteres": criteres,
            "profil": {
                "abonnes": followers,
                "engagement": engagement,
                "verified": data['verified'],
                "videos": data['statistiques']['videos'],
                "niches": data['niches']
            },
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"erreur": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5008)
