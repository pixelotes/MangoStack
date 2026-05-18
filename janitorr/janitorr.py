#!/usr/bin/env python3
import argparse
import re
import json
import logging
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from difflib import SequenceMatcher

# --- Customizable Settings ---

# Media file extensions to look for
MEDIA_EXTENSIONS = {'.mkv', '.mp4', '.avi', '.ts', '.m4v', '.mov', '.wmv', '.flv', '.webm'}

# Folders to ignore when scanning for movies (case-insensitive)
EXTRAS_FOLDERS = {'extras', 'bonus', 'behind the scenes', 'deleted scenes', 'featurettes', 'trailers', 'samples'}

# Minimum file size in MB to consider (helps filter out samples/trailers)
MIN_FILE_SIZE_MB = 100

# Define the value of each quality component. Higher is better.
QUALITY_SCORES = {
    # Resolution
    '4k': 8, '2160p': 8, 'uhd': 8,
    '1440p': 6, '2k': 6,
    '1080p': 5, 'fhd': 5,
    '720p': 4, 'hd': 4,
    '480p': 3, 'sd': 2,
    '360p': 1, 'msd': 1,
    # Source quality
    'remux': 10,
    'bluray': 8, 'blu-ray': 8, 'bdrip': 8, 'brrip': 6,
    'webdl': 7, 'web-dl': 7, 'web': 6, 'webrip': 5,
    'hdtv': 4, 'pdtv': 3, 'dvdrip': 3, 'dvd': 3,
    'cam': 1, 'ts': 1, 'tc': 1,
    # Codec (modern codecs get bonus points)
    'av1': 5,
    'x265': 3, 'h265': 3, 'hevc': 3,
    'x264': 2, 'h264': 2, 'avc': 2,
    'xvid': 1, 'divx': 1,
    # Audio quality
    'atmos': 3, 'truehd': 3, 'dts-hd': 3, 'dts-x': 3,
    'dts': 2, 'ac3': 1, 'aac': 1,
    # Special indicators
    'repack': 1, 'proper': 1, 'real': 1,
    'extended': 1, 'uncut': 1, 'directors': 1,
    'hdr': 2, 'hdr10': 2, 'dolbyvision': 3, 'dv': 3,
    # Movie-specific quality indicators
    'imax': 2, 'criterion': 2, 'remastered': 1,
    'anniversary': 1, 'collectors': 1, 'special': 1,
    'theatrical': 0, 'director': 1, 'extended': 1,
}

# --- End of Settings ---

def setup_logging(verbose=False):
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('janitorr.log')
        ]
    )

def get_quality_score(quality_string, file_size_mb=0, prefer_smaller=False):
    """Calculates a numerical score based on the quality string and optionally file size."""
    score = 0
    quality_string = quality_string.lower()
    
    # Quality-based scoring
    for key, value in QUALITY_SCORES.items():
        if key in quality_string:
            score += value
    
    # Optional file size consideration (smaller = better if prefer_smaller is True)
    if prefer_smaller and file_size_mb > 0:
        # Subtract a small penalty for larger files (max 2 points)
        size_penalty = min(2, file_size_mb / 10000)  # 10GB = 1 point penalty
        score -= size_penalty
    
    return score

def get_file_size_mb(file_path):
    """Get file size in MB."""
    try:
        return file_path.stat().st_size / (1024 * 1024)
    except OSError:
        return 0

def similarity(a, b):
    """Calculate similarity between two strings."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def normalize_title(title):
    """Normalize movie/series title for comparison."""
    # Remove common articles and normalize spacing
    title = re.sub(r'^(the|a|an)\s+', '', title.lower())
    title = re.sub(r'[._\-\s]+', ' ', title).strip()
    # Remove special characters but keep alphanumeric and spaces
    title = re.sub(r'[^\w\s]', '', title)
    return title

def parse_episode_info(filename):
    """Parse episode information from filename using more flexible approach."""
    # Pattern to find SxxExx or SxExx format, including multi-episode patterns
    episode_pattern = re.compile(r'[Ss](\d{1,2})[Ee](\d{2,})(?:[-Ee](\d{2,}))?', re.IGNORECASE)
    match = episode_pattern.search(filename)
    
    if not match:
        return None
    
    season = int(match.group(1))
    episode_start = int(match.group(2))
    episode_end = int(match.group(3)) if match.group(3) else episode_start
    
    # Create episode ID that handles multi-episode files
    if episode_start == episode_end:
        episode_id = f"S{season:02d}E{episode_start:02d}"
    else:
        episode_id = f"S{season:02d}E{episode_start:02d}-E{episode_end:02d}"
    
    # Extract series name (everything before the episode pattern)
    series_end = match.start()
    series_name_raw = filename[:series_end]
    
    # Clean up series name more aggressively
    series_name_normalized = normalize_title(series_name_raw)
    # Remove year patterns that might interfere
    series_name_normalized = re.sub(r'\b(19|20)\d{2}\b', '', series_name_normalized).strip()
    
    # Everything after the episode pattern is quality info
    quality_info = filename[match.end():]
    
    return {
        'series_name': series_name_normalized,
        'episode_id': episode_id,
        'quality_info': quality_info,
        'is_multi_episode': episode_start != episode_end
    }

def parse_movie_info(file_path):
    """Parse movie information from file path (folder name preferred, filename as fallback)."""
    # Try folder name first (more reliable for movie organization)
    folder_name = file_path.parent.name
    filename = file_path.stem
    
    # Check if folder name looks like a movie (has year or is meaningful)
    folder_year_match = re.search(r'\b(19|20)\d{2}\b', folder_name)
    
    if folder_year_match and len(folder_name.strip()) > 8:  # Use folder if it has year and is substantial
        title_source = folder_name
        is_from_folder = True
    else:
        title_source = filename
        is_from_folder = False
    
    # Extract year
    year_match = re.search(r'\b((19|20)\d{2})\b', title_source)
    year = year_match.group(1) if year_match else None
    
    # Extract title (everything before the year, or before quality indicators)
    if year_match:
        title_end = year_match.start()
        title_raw = title_source[:title_end]
    else:
        # If no year, try to find where quality info starts
        quality_indicators = ['1080p', '720p', '480p', '4k', '2160p', 'bluray', 'webrip', 'webdl', 'hdtv', 'x264', 'x265']
        title_end = len(title_source)
        for indicator in quality_indicators:
            match = re.search(re.escape(indicator), title_source, re.IGNORECASE)
            if match:
                title_end = min(title_end, match.start())
        title_raw = title_source[:title_end]
    
    # Clean up title
    title_normalized = normalize_title(title_raw)
    
    # Extract quality info (everything after title/year)
    if year_match:
        quality_start = year_match.end()
    else:
        quality_start = len(title_raw)
    quality_info = title_source[quality_start:]
    
    # Create unique movie identifier
    movie_id = f"{title_normalized}"
    if year:
        movie_id += f" ({year})"
    
    return {
        'title': title_normalized,
        'year': year,
        'movie_id': movie_id,
        'quality_info': quality_info,
        'is_from_folder': is_from_folder,
        'folder_path': file_path.parent
    }

def is_extras_folder(folder_path):
    """Check if folder appears to contain extras/bonus content."""
    folder_name_lower = folder_path.name.lower()
    return any(extra in folder_name_lower for extra in EXTRAS_FOLDERS)

def find_tv_duplicates(directory, include_patterns=None, exclude_patterns=None, prefer_smaller=False):
    """Finds and groups duplicate TV episodes using improved parsing."""
    print(f"🔍 Scanning TV directory recursively: {directory}")
    
    # Get all media files
    all_files = list(Path(directory).rglob('*'))
    media_files = [p for p in all_files if p.suffix.lower() in MEDIA_EXTENSIONS]
    
    # Apply include/exclude filters
    if include_patterns:
        media_files = [f for f in media_files if any(re.search(pattern, f.name, re.IGNORECASE) for pattern in include_patterns)]
    
    if exclude_patterns:
        media_files = [f for f in media_files if not any(re.search(pattern, f.name, re.IGNORECASE) for pattern in exclude_patterns)]

    parsed_files = []

    # --- PASS 1: Parse all files and store their info ---
    print(f"📄 Pass 1: Parsing {len(media_files)} TV media files...")
    for file_path in media_files:
        episode_info = parse_episode_info(file_path.stem)
        
        if episode_info:
            file_size_mb = get_file_size_mb(file_path)
            quality_score = get_quality_score(episode_info['quality_info'], file_size_mb, prefer_smaller)
            
            parsed_files.append({
                'path': file_path,
                'series_key': episode_info['series_name'],
                'episode_key': episode_info['episode_id'],
                'quality_info': episode_info['quality_info'],
                'score': quality_score,
                'size_mb': file_size_mb,
                'is_multi_episode': episode_info.get('is_multi_episode', False)
            })
            
            logging.debug(f"Parsed TV: {episode_info['series_name']} {episode_info['episode_id']} "
                         f"(score: {quality_score:.1f}, size: {file_size_mb:.1f}MB) - {file_path.name}")
        else:
            logging.warning(f"Could not parse episode info from: {file_path.name}")

    # --- PASS 2: Group parsed files by unique episode key ---
    print(f"\n📊 Pass 2: Grouping {len(parsed_files)} parsed TV files to find duplicates...")
    episodes = defaultdict(list)
    for file_info in parsed_files:
        unique_key = (file_info['series_key'], file_info['episode_key'])
        episodes[unique_key].append(file_info)

    # Filter for only those episodes that have duplicates
    duplicates = {key: files for key, files in episodes.items() if len(files) > 1}
    
    print(f"🔍 Found {len(duplicates)} TV episodes with duplicates")
    return duplicates

def find_movie_duplicates(directory, include_patterns=None, exclude_patterns=None, prefer_smaller=False, 
                         min_size_mb=MIN_FILE_SIZE_MB, fuzzy_matching=False, ignore_extras=True):
    """Finds and groups duplicate movies using folder-based and title-based detection."""
    print(f"🔍 Scanning movie directory recursively: {directory}")
    
    # Get all media files
    all_files = list(Path(directory).rglob('*'))
    media_files = [p for p in all_files if p.suffix.lower() in MEDIA_EXTENSIONS]
    
    # Filter out extras folders if requested
    if ignore_extras:
        media_files = [f for f in media_files if not is_extras_folder(f.parent)]
    
    # Filter by minimum size
    media_files = [f for f in media_files if get_file_size_mb(f) >= min_size_mb]
    
    # Apply include/exclude filters
    if include_patterns:
        media_files = [f for f in media_files if any(re.search(pattern, f.name, re.IGNORECASE) for pattern in include_patterns)]
    
    if exclude_patterns:
        media_files = [f for f in media_files if not any(re.search(pattern, f.name, re.IGNORECASE) for pattern in exclude_patterns)]

    parsed_files = []
    folder_groups = defaultdict(list)

    # --- PASS 1: Parse all files and group by folder ---
    print(f"📄 Pass 1: Parsing {len(media_files)} movie files...")
    for file_path in media_files:
        movie_info = parse_movie_info(file_path)
        file_size_mb = get_file_size_mb(file_path)
        quality_score = get_quality_score(movie_info['quality_info'], file_size_mb, prefer_smaller)
        
        file_info = {
            'path': file_path,
            'movie_id': movie_info['movie_id'],
            'title': movie_info['title'],
            'year': movie_info['year'],
            'quality_info': movie_info['quality_info'],
            'score': quality_score,
            'size_mb': file_size_mb,
            'folder_path': movie_info['folder_path']
        }
        
        parsed_files.append(file_info)
        folder_groups[movie_info['folder_path']].append(file_info)
        
        logging.debug(f"Parsed Movie: {movie_info['movie_id']} "
                     f"(score: {quality_score:.1f}, size: {file_size_mb:.1f}MB) - {file_path.name}")

    # --- PASS 2: Find folder-based duplicates ---
    print(f"\n📊 Pass 2: Finding folder-based duplicates...")
    folder_duplicates = {}
    
    for folder_path, files in folder_groups.items():
        if len(files) > 1:
            # Multiple files in same folder = duplicates
            folder_key = f"FOLDER: {folder_path.name}"
            folder_duplicates[folder_key] = files
            print(f"  Found {len(files)} files in folder: {folder_path.name}")

    # --- PASS 3: Find title-based duplicates across different folders ---
    print(f"\n📊 Pass 3: Finding title-based duplicates across folders...")
    title_groups = defaultdict(list)
    
    # Group by movie_id (title + year)
    for file_info in parsed_files:
        # Skip files already found as folder duplicates
        if any(file_info in files for files in folder_duplicates.values()):
            continue
        title_groups[file_info['movie_id']].append(file_info)
    
    title_duplicates = {}
    for movie_id, files in title_groups.items():
        if len(files) > 1:
            title_duplicates[f"TITLE: {movie_id}"] = files
            folders = [f['folder_path'].name for f in files]
            print(f"  Found {len(files)} copies of '{movie_id}' across folders: {', '.join(folders)}")

    # --- PASS 4: Fuzzy matching for similar titles (optional) ---
    fuzzy_duplicates = {}
    if fuzzy_matching:
        print(f"\n📊 Pass 4: Fuzzy matching for similar titles...")
        processed_titles = set()
        
        for file_info in parsed_files:
            if file_info['movie_id'] in processed_titles:
                continue
            if any(file_info in files for files in {**folder_duplicates, **title_duplicates}.values()):
                continue
                
            similar_files = [file_info]
            processed_titles.add(file_info['movie_id'])
            
            for other_file in parsed_files:
                if other_file['movie_id'] == file_info['movie_id']:
                    continue
                if other_file['movie_id'] in processed_titles:
                    continue
                if any(other_file in files for files in {**folder_duplicates, **title_duplicates}.values()):
                    continue
                
                # Check similarity between titles
                title_sim = similarity(file_info['title'], other_file['title'])
                year_match = (file_info['year'] == other_file['year']) if (file_info['year'] and other_file['year']) else True
                
                if title_sim >= 0.85 and year_match:  # 85% similarity threshold
                    similar_files.append(other_file)
                    processed_titles.add(other_file['movie_id'])
            
            if len(similar_files) > 1:
                fuzzy_key = f"FUZZY: {file_info['title']}"
                if file_info['year']:
                    fuzzy_key += f" ({file_info['year']})"
                fuzzy_duplicates[fuzzy_key] = similar_files
                folders = [f['folder_path'].name for f in similar_files]
                print(f"  Found {len(similar_files)} similar titles: {fuzzy_key} across folders: {', '.join(folders)}")

    # Combine all duplicate types
    all_duplicates = {**folder_duplicates, **title_duplicates, **fuzzy_duplicates}
    
    total_duplicate_files = sum(len(files) for files in all_duplicates.values())
    print(f"🔍 Found {len(all_duplicates)} movie duplicate groups ({total_duplicate_files} total files)")
    print(f"  - Folder-based: {len(folder_duplicates)} groups")
    print(f"  - Title-based: {len(title_duplicates)} groups")
    if fuzzy_matching:
        print(f"  - Fuzzy-matched: {len(fuzzy_duplicates)} groups")
    
    return all_duplicates

def create_backup_list(files_to_delete, backup_file='janitorr_backup.json'):
    """Create a JSON backup of files that will be deleted."""
    backup_data = {
        'timestamp': datetime.now().isoformat(),
        'files': []
    }
    
    for file_info in files_to_delete:
        backup_entry = {
            'path': str(file_info['path']),
            'score': file_info['score'],
            'size_mb': file_info['size_mb']
        }
        
        # Add appropriate metadata based on content type
        if 'series_key' in file_info:  # TV episode
            backup_entry.update({
                'series': file_info['series_key'],
                'episode': file_info['episode_key']
            })
        else:  # Movie
            backup_entry.update({
                'movie_id': file_info['movie_id'],
                'title': file_info['title'],
                'year': file_info['year']
            })
        
        backup_data['files'].append(backup_entry)
    
    with open(backup_file, 'w') as f:
        json.dump(backup_data, f, indent=2)
    
    print(f"📋 Backup list created: {backup_file}")

def interactive_confirmation(duplicates, reverse_mode=False, content_type="items"):
    """Interactive confirmation for each duplicate group."""
    confirmed_deletions = []
    
    for group_key, files in duplicates.items():
        files.sort(key=lambda x: x['score'])
        
        if reverse_mode:
            file_to_keep = files[0]
            files_to_delete = files[1:]
            mode_desc = "LOWEST quality"
        else:
            file_to_keep = files[-1]
            files_to_delete = files[:-1]
            mode_desc = "HIGHEST quality"
        
        print(f"\n▶️  {group_key}")
        print(f"  Files found:")
        for i, f in enumerate(files):
            marker = "✅ KEEP" if f == file_to_keep else "❌ DELETE"
            folder_info = f" (in: {f['folder_path'].name})" if 'folder_path' in f else ""
            print(f"    {i+1}. {marker} (score: {f['score']:.1f}, {f['size_mb']:.1f}MB){folder_info}")
            print(f"        {f['path'].name}")
        
        print(f"\n  Will keep {mode_desc} file: {file_to_keep['path'].name}")
        
        response = input("  Proceed with deletion? [y/N/s(kip all)/q(uit)]: ").lower().strip()
        
        if response == 'q':
            print("Quitting...")
            break
        elif response == 's':
            print("Skipping all remaining duplicates...")
            break
        elif response == 'y':
            confirmed_deletions.extend(files_to_delete)
        else:
            print("  Skipped.")
    
    return confirmed_deletions

def delete_file_with_sidecars(path_to_delete, dry_run=False):
    """Deletes a media file and its associated sidecar files."""
    files_to_remove = [path_to_delete]

    # Find sidecar files (e.g., .srt, .nfo, .jpg) with the same stem
    try:
        for sibling in path_to_delete.parent.iterdir():
            if sibling.stem == path_to_delete.stem and sibling != path_to_delete:
                files_to_remove.append(sibling)
    except OSError:
        pass  # Handle case where parent directory is not accessible

    for file in files_to_remove:
        print(f"  ❌ DELETING: {file.name}")
        if not dry_run:
            try:
                file.unlink()
                print(f"    -> Successfully deleted.")
            except OSError as e:
                print(f"    -> ERROR: Could not delete file. {e}")

def main():
    parser = argparse.ArgumentParser(description="Find and delete duplicate TV episodes and movies based on quality scores.")
    parser.add_argument('-d', '--directory', required=True, help="The media library directory to scan.")
    parser.add_argument('--mode', choices=['tv', 'movie', 'auto'], default='auto', 
                       help="Content type to scan for (default: auto-detect).")
    parser.add_argument('--dry-run', action='store_true', help="Print what would be deleted without actually deleting files.")
    parser.add_argument('--reverse', action='store_true', help="Keep the lower quality file instead of the higher quality one.")
    parser.add_argument('--prefer-smaller', action='store_true', help="Prefer smaller file sizes when scoring quality.")
    parser.add_argument('--interactive', action='store_true', help="Interactively confirm each deletion.")
    parser.add_argument('--include', nargs='+', help="Include only files matching these regex patterns.")
    parser.add_argument('--exclude', nargs='+', help="Exclude files matching these regex patterns.")
    parser.add_argument('--backup', help="Create a JSON backup file of deletions (default: janitorr_backup.json).")
    parser.add_argument('-v', '--verbose', action='store_true', help="Enable verbose logging.")
    
    # Movie-specific options
    parser.add_argument('--min-size-mb', type=int, default=MIN_FILE_SIZE_MB,
                       help=f"Minimum file size in MB to consider (default: {MIN_FILE_SIZE_MB}).")
    parser.add_argument('--fuzzy-matching', action='store_true', 
                       help="Enable fuzzy title matching for movies (finds similar titles).")
    parser.add_argument('--keep-extras', action='store_true', 
                       help="Don't ignore extras/bonus folders (default: ignores extras).")
    
    args = parser.parse_args()

    # Setup logging
    setup_logging(args.verbose)

    if args.dry_run:
        print("--- DRY RUN MODE --- No files will be deleted. ---")
    
    if args.reverse:
        print("--- REVERSE MODE --- Keeping lower quality files instead of higher quality ones. ---")
    
    if args.prefer_smaller:
        print("--- PREFER SMALLER --- File size will be considered in quality scoring. ---")

    # Auto-detect content type if not specified
    directory_path = Path(args.directory)
    if args.mode == 'auto':
        print("🔍 Auto-detecting content type...")
        sample_files = list(directory_path.rglob('*.mkv'))[:20]  # Sample first 20 mkv files
        tv_count = sum(1 for f in sample_files if parse_episode_info(f.stem))
        movie_count = len(sample_files) - tv_count
        
        if tv_count > movie_count:
            detected_mode = 'tv'
            print(f"📺 Detected TV content ({tv_count} TV files vs {movie_count} movie files in sample)")
        else:
            detected_mode = 'movie'
            print(f"🎬 Detected movie content ({movie_count} movie files vs {tv_count} TV files in sample)")
        args.mode = detected_mode

    # Find duplicates based on mode
    if args.mode == 'tv':
        duplicates = find_tv_duplicates(args.directory, args.include, args.exclude, args.prefer_smaller)
        content_type = "TV episodes"
    else:  # movie mode
        duplicates = find_movie_duplicates(
            args.directory, args.include, args.exclude, args.prefer_smaller,
            args.min_size_mb, args.fuzzy_matching, not args.keep_extras
        )
        content_type = "movies"

    if not duplicates:
        print(f"✅ No duplicate {content_type} found.")
        return

    print(f"\n--- Processing {content_type.title()} Duplicates ---")
    
    if args.interactive:
        files_to_delete = interactive_confirmation(duplicates, args.reverse, content_type)
        if not files_to_delete:
            print("No files selected for deletion.")
            return
        
        # Create backup if requested
        if args.backup or args.backup is None:
            backup_file = args.backup if args.backup else 'janitorr_backup.json'
            create_backup_list(files_to_delete, backup_file)
        
        # Delete confirmed files
        total_deleted = len(files_to_delete)
        for file_info in files_to_delete:
            delete_file_with_sidecars(file_info['path'], args.dry_run)
    else:
        # Automatic mode
        total_deleted = 0
        files_to_delete = []
        
        for group_key, files in duplicates.items():
            # Sort by score (lowest to highest)
            files.sort(key=lambda x: x['score'])

            if args.reverse:
                # In reverse mode, keep the lowest quality (first after sort)
                file_to_keep = files[0]
                files_to_delete_group = files[1:]
                mode_desc = "REVERSE MODE - Keeping LOWEST quality"
            else:
                # Normal mode, keep the highest quality (last after sort)
                file_to_keep = files[-1]
                files_to_delete_group = files[:-1]
                mode_desc = "Keeping HIGHEST quality"

            print(f"\n▶️  {group_key} ({mode_desc})")
            print(f"  ✅ KEEPING : (score: {file_to_keep['score']:.1f}) {file_to_keep['path'].name}")

            for file_info in files_to_delete_group:
                print(f"  🗑️  DELETING: (score: {file_info['score']:.1f}) {file_info['path'].name}")
                delete_file_with_sidecars(file_info['path'], args.dry_run)
                total_deleted += 1
                files_to_delete.append(file_info)

        # Create backup if requested
        if (args.backup or args.backup is None) and files_to_delete and not args.dry_run:
            backup_file = args.backup if args.backup else 'janitorr_backup.json'
            create_backup_list(files_to_delete, backup_file)

    print(f"\n📈 Summary: {total_deleted} files marked for deletion across {len(duplicates)} duplicate groups")
    if args.dry_run:
        print("   (No files were actually deleted due to dry-run mode)")

if __name__ == "__main__":
    main()
