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

async def trigger_audio_generation():
    print('🎧 Starting audio generation process...')
    print(f'📅 Started at: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Get homepage data to find clusters with syntheses
            print('📡 Fetching homepage data...')
            response = await client.get('http://localhost:5001/api/home')
            
            if response.status_code == 200:
                data = response.json()
                clusters = data.get('clusters', []) + data.get('global', [])
                
                print(f'📊 Found {len(clusters)} clusters on homepage')
                
                if not clusters:
                    print('⚠️ No clusters found on homepage')
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
                    
                    print(f'🎤 [{i}/{len(clusters)}] Checking cluster {cluster_id} ({lang})...')
                    
                    # Check if cluster has synthesis by trying to get audio
                    try:
                        audio_response = await client.get(
                            f'http://localhost:5001/api/cluster/{cluster_id}/audio',
                            params={'lang': lang}
                        )
                        
                        if audio_response.status_code == 200:
                            audio_data = audio_response.json()
                            if audio_data.get('status') == 'success':
                                if 'already exists' in audio_data.get('message', '').lower():
                                    print(f'✅ Audio already exists for cluster {cluster_id}')
                                    audio_existed += 1
                                else:
                                    audio_url = audio_data.get('audio_url')
                                    print(f'🎉 Audio generated for cluster {cluster_id}: {audio_url}')
                                    audio_generated += 1
                            else:
                                print(f'⚠️ Audio check failed for cluster {cluster_id}: {audio_data.get("message")}')
                                errors += 1
                        elif audio_response.status_code == 404:
                            print(f'❌ Cluster {cluster_id} has no synthesis')
                            no_synthesis += 1
                        else:
                            print(f'💥 Error checking cluster {cluster_id}: HTTP {audio_response.status_code}')
                            errors += 1
                    except Exception as e:
                        print(f'💥 Error processing cluster {cluster_id}: {e}')
                        errors += 1
                
                print(f'\n📈 Audio Generation Summary:')
                print(f'🎉 New audio files generated: {audio_generated}')
                print(f'✅ Existing audio files: {audio_existed}')
                print(f'❌ Clusters without synthesis: {no_synthesis}')
                print(f'💥 Errors: {errors}')
                print(f'🎧 Total clusters processed: {len(clusters)}')
                print(f'📅 Completed at: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
                
            else:
                print(f'❌ Failed to fetch homepage: HTTP {response.status_code}')
                print('💡 Make sure the Presek server is running on http://localhost:5001')
    except Exception as e:
        print(f'💥 Error during audio generation: {e}')
        print('💡 Make sure the Presek server is running and accessible')

if __name__ == '__main__':
    print('🎧 Cluster Audio Generation Script')
    print('================================')
    print('This script generates audio files for clusters that have syntheses.')
    print('Make sure the Presek server is running before executing this script.\n')
    
    asyncio.run(trigger_audio_generation())