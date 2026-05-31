#!/usr/bin/env python3
"""
Cluster Audio Generation Script
Generates audio files for clusters that have syntheses
"""

import asyncio
import sys
import os
sys.path.append('.')
os.environ['ENV'] = 'development'

import httpx
import json
from datetime import datetime

API_BASE_URL = os.environ.get('PRESEK_API_BASE_URL', 'http://127.0.0.1:5001')

def collect_homepage_clusters(data):
    """Collect cluster-shaped objects from the homepage response."""
    clusters = []
    seen = set()
    sections = [
        data.get('lead'),
        *(data.get('supporting') or []),
        *(data.get('live_now') or []),
        *(data.get('for_you_pool') or []),
        *(data.get('developing') or []),
        *(data.get('wire') or []),
        *(data.get('global') or []),
        *(data.get('clusters') or []),
    ]

    for cluster in sections:
        if not isinstance(cluster, dict):
            continue
        cluster_id = cluster.get('cluster_id')
        if not cluster_id or cluster_id in seen:
            continue
        seen.add(cluster_id)
        clusters.append(cluster)

    return clusters

async def trigger_audio_generation():
    print('🎧 Starting audio generation process...', flush=True)
    print(f'📅 Started at: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', flush=True)
    print(f'🔌 API base URL: {API_BASE_URL}', flush=True)
    
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0)) as client:
            # Get homepage data to find clusters with syntheses
            print('📡 Fetching homepage data...', flush=True)
            response = await client.get(f'{API_BASE_URL}/api/home')
            
            if response.status_code == 200:
                data = response.json()
                clusters = collect_homepage_clusters(data)
                
                print(f'📊 Found {len(clusters)} clusters on homepage', flush=True)
                
                if not clusters:
                    print('⚠️ No clusters found on homepage', flush=True)
                    return
                
                audio_generated = 0
                audio_existed = 0
                errors = 0
                no_synthesis = 0
                
                for i, cluster in enumerate(clusters, 1):
                    cluster_id = cluster.get('cluster_id')
                    lang = cluster.get('lang', 'sr')
                    
                    if not cluster_id:
                        continue
                    
                    print(f'🎤 [{i}/{len(clusters)}] Checking cluster {cluster_id} ({lang})...', flush=True)
                    
                    # Check if cluster has synthesis by trying to get audio
                    try:
                        audio_response = await client.get(
                            f'{API_BASE_URL}/api/cluster/{cluster_id}/audio',
                            params={'lang': lang}
                        )
                        
                        if audio_response.status_code == 200:
                            audio_data = audio_response.json()
                            if audio_data.get('status') == 'success':
                                if 'already exists' in audio_data.get('message', '').lower():
                                    print(f'✅ Audio already exists for cluster {cluster_id}', flush=True)
                                    audio_existed += 1
                                else:
                                    audio_url = audio_data.get('audio_url')
                                    print(f'🎉 Audio generated for cluster {cluster_id}: {audio_url}', flush=True)
                                    audio_generated += 1
                            else:
                                print(f'⚠️ Audio check failed for cluster {cluster_id}: {audio_data.get("message")}', flush=True)
                                errors += 1
                        elif audio_response.status_code == 404:
                            print(f'❌ Cluster {cluster_id} has no synthesis', flush=True)
                            no_synthesis += 1
                        else:
                            print(f'💥 Error checking cluster {cluster_id}: HTTP {audio_response.status_code}', flush=True)
                            errors += 1
                    except Exception as e:
                        print(f'💥 Error processing cluster {cluster_id}: {e}', flush=True)
                        errors += 1
                
                print(f'\n📈 Audio Generation Summary:', flush=True)
                print(f'🎉 New audio files generated: {audio_generated}', flush=True)
                print(f'✅ Existing audio files: {audio_existed}', flush=True)
                print(f'❌ Clusters without synthesis: {no_synthesis}', flush=True)
                print(f'💥 Errors: {errors}', flush=True)
                print(f'🎧 Total clusters processed: {len(clusters)}', flush=True)
                print(f'📅 Completed at: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', flush=True)
                
            else:
                print(f'❌ Failed to fetch homepage: HTTP {response.status_code}', flush=True)
                print(f'💡 Make sure the Presek server is running on {API_BASE_URL}', flush=True)
    except Exception as e:
        print(f'💥 Error during audio generation: {e}', flush=True)
        print('💡 Make sure the Presek server is running and accessible')

if __name__ == '__main__':
    print('🎧 Cluster Audio Generation Script')
    print('================================')
    print('This script generates audio files for clusters that have syntheses.')
    print('Make sure the Presek server is running before executing this script.\n')
    
    asyncio.run(trigger_audio_generation())
