import requests
import platform
import json
import re
import textwrap
import shutil
import threading
import os
import subprocess
import gc
from colorama import Fore, Style
import time
import ebooklib
from ebooklib import epub
import html
from datetime import datetime
import signal


keep_alive_running = False

def deduplicate_chapters(full_novel):
    """Remove duplicate chapters from the novel text"""
    color_print("Checking for and removing duplicate chapters...", Fore.CYAN)
    
    # Split the novel by chapter headers
    chapter_pattern = re.compile(r'(Chapter\s+\d+[:\s]+.*?\n)', re.IGNORECASE)
    parts = chapter_pattern.split(full_novel)
    
    # Rebuild the novel without duplicates
    processed_novel = ""
    seen_chapters = set()
    current_content = ""
    
    i = 0
    while i < len(parts):
        if i + 1 < len(parts) and chapter_pattern.match(parts[i]):
            # This is a chapter header
            chapter_header = parts[i]
            chapter_match = re.search(r'Chapter\s+(\d+)[:\s]+(.*?)\n', chapter_header, re.IGNORECASE)
            
            if chapter_match:
                chapter_num = chapter_match.group(1)
                chapter_title = chapter_match.group(2).strip()
                chapter_key = f"{chapter_num}:{chapter_title}"
                
                if chapter_key in seen_chapters:
                    # This is a duplicate chapter, skip it and its content
                    color_print(f"Found duplicate: Chapter {chapter_num}: {chapter_title}", Fore.YELLOW)
                    # Skip the header and content
                    i += 2
                    continue
                else:
                    # New chapter, add it to seen chapters
                    seen_chapters.add(chapter_key)
                    
                    # Add previous content if any
                    if current_content:
                        processed_novel += current_content
                        current_content = ""
                    
                    # Add the header
                    processed_novel += chapter_header
                    
                    # Get the chapter content if available
                    if i + 1 < len(parts):
                        current_content = parts[i + 1]
                    
                    i += 2
            else:
                # Not a properly formatted chapter header, treat as regular content
                processed_novel += parts[i]
                i += 1
        else:
            # Regular content, add it
            processed_novel += parts[i]
            i += 1
    
    # Add the last content section if any
    if current_content:
        processed_novel += current_content
    
    color_print(f"Deduplication complete. Removed {len(full_novel.split()) - len(processed_novel.split())} words.", Fore.GREEN)
    return processed_novel

# Add keep-alive functionality to prevent sleep
def setup_keep_alive():
    """Set up a more robust keep-alive mechanism to prevent system sleep during long operations"""
    global keep_alive_running
    
    # Set the flag to True to start the thread
    keep_alive_running = True
    
    # Create and start a thread that will continually prevent sleep
    def keep_alive_thread():
        system = platform.system().lower()
        color_print("Starting keep-alive thread to prevent system sleep...", Fore.CYAN)
        
        while keep_alive_running:
            # Print a dot to show activity in the terminal
            print(".", end="", flush=True)
            
            # Perform platform-specific actions to prevent sleep
            try:
                if system == "darwin":  # macOS
                    # Use caffeinate to prevent sleep (if available)
                    subprocess.call(["caffeinate", "-i", "-t", "59"])
                elif system == "windows":
                    # Simulate user activity on Windows
                    import ctypes
                    ctypes.windll.kernel32.SetThreadExecutionState(0x80000003)  # ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
                elif system == "linux":
                    # On Linux, try using xdg-screensaver
                    subprocess.call(["xdg-screensaver", "reset"])
            except Exception as e:
                # If these methods fail, just continue with the basic approach
                pass
            
            # Sleep for 30 seconds before the next keep-alive action
            for _ in range(30):
                if not keep_alive_running:
                    break
                time.sleep(1)
    
    # Start the keep-alive thread
    thread = threading.Thread(target=keep_alive_thread, daemon=True)
    thread.start()
    return True

def cancel_keep_alive():
    """Cancel the keep-alive mechanism"""
    global keep_alive_running
    keep_alive_running = False
    return True

def color_print(text, color=Fore.WHITE, width=None):
    if not text:
        return
        
    try:
        columns, _ = shutil.get_terminal_size(fallback=(80, 20))
    except:
        columns = 80
    width = width or columns
    
    # Handle ANSI color codes when calculating width
    stripped_text = re.sub(r'\x1B\[[0-?]*[ -/]*[@-~]', '', text)
    paragraphs = stripped_text.split('\n')
    
    for para in paragraphs:
        if not para.strip():
            print()
            continue
        wrapped_lines = textwrap.wrap(
            textwrap.dedent(para).strip(),
            width=width,
            replace_whitespace=False,
            drop_whitespace=False
        )
        for line in wrapped_lines:
            print(f"{color}{line}{Style.RESET_ALL}")

def create_story_plan(title, theme=None, genre=None, max_tokens=4000, additional_instructions=None):
    """Create a structured outline for the story with JSON chapter details"""
    
    color_print(f"\nCreating detailed story plan for: {title}\n", Fore.CYAN)
    
    # First, build the prompt parts
    prompt_parts = [
        f"""Create an extremely detailed story plan for a novel titled "{title}"."""
    ]
    
    if theme:
        prompt_parts.append(f'Theme: {theme}')
    if genre:
        prompt_parts.append(f'Genre: {genre}')
    
    prompt_parts.append("""
The plan should include:

1. PREMISE: A comprehensive summary of the core story concept.

2. CHARACTERS:
   - Main character(s): Detailed background, psychology, key traits, wants, needs, internal conflicts, and development arc
   - Supporting characters: Thorough descriptions, motivations, and their relationship to the protagonist
   - Antagonists: Complex motivations, backstory, and detailed conflicts with the protagonist

3. NARRATIVE STRUCTURE:
   - Beginning: Detailed opening scenes, character introductions, and world-building elements
   - Middle: Elaborate central conflicts, complications, and escalating tensions
   - Multiple plot points and subplots with interconnections
   - Climax: Detailed description of the turning point and its impact on all characters
   - Resolution: Comprehensive conclusion showing how character arcs and themes are resolved

4. KEY SCENES: 15-20 essential scenes that drive the narrative forward, with detailed descriptions

5. SETTINGS: Expansive descriptions of all locations, including sensory details and significance to the story

6. THEME & MESSAGE: In-depth exploration of core ideas and how they manifest throughout the story

7. DETAILED CHAPTER BREAKDOWN: 
   Provide a detailed chapter-by-chapter breakdown with EXACTLY this format for EACH chapter:

   Chapter 1: [Title]
   [Detailed 150-200 word description of the chapter events, character development, and plot advancement]

   Chapter 2: [Title]
   [Detailed 150-200 word description of the chapter events, character development, and plot advancement]

   ...and so on. Provide at least 20 chapters, each with detailed descriptions.
""")
    
    # Add any additional instructions
    if additional_instructions:
        prompt_parts.append(additional_instructions)
    
    # Join all prompt parts together
    prompt = "\n\n".join(prompt_parts)
    
    try:
        start_time = time.time()
        color_print("Generating comprehensive story plan...", Fore.YELLOW)
        
        keep_alive_running = setup_keep_alive()
        if keep_alive_running:
            color_print("Keep-alive feature enabled to prevent system sleep", Fore.CYAN)
        
        response = requests.post(
            "http://localhost:8080/completion",
            json={
                "prompt": prompt,
                "max_tokens": max_tokens,
                "stream": True
            },
            stream=True
        )
        
        if response.status_code != 200:
            color_print(f"\nAPI Error: Status code {response.status_code}", Fore.RED)
            cancel_keep_alive()
            return None
            
        full_response = ""
        buffer = ""
        color_print("\nGenerating plan... \n", Fore.YELLOW)
        
        for line in response.iter_lines():
            if line:
                try:
                    decoded_line = line.decode('utf-8')
                    if decoded_line.startswith('data: '):
                        json_data = json.loads(decoded_line[6:])
                        content = json_data.get('content', '')
                        buffer += content
                        full_response += content
                        
                        if content and content[-1] in (' ', '.', ',', '!', '?', '\n'):
                            color_print(buffer, Fore.CYAN)
                            buffer = ""
                except json.JSONDecodeError:
                    color_print("\nError decoding JSON from API response", Fore.RED)
                except Exception as e:
                    color_print(f"\nError processing stream: {e}", Fore.RED)
        
        if buffer:
            color_print(buffer, Fore.CYAN)
        
        cancel_keep_alive()
        end_time = time.time()
        duration = end_time - start_time
        color_print(f"\n\nPlan generation complete in {duration:.2f} seconds!", Fore.GREEN)
        
        return full_response.strip()
        
    except requests.RequestException as e:
        color_print(f"\nAPI Connection Error: {e}", Fore.RED)
        cancel_keep_alive()
        return None
    except Exception as e:
        color_print(f"\nUnexpected Error: {e}", Fore.RED)
        cancel_keep_alive()
        return None

def extract_chapters(story_plan):
    """Extract chapter data from the story plan using regex"""
    
    # Look for chapter patterns in the format "Chapter X: Title - Description"
    chapter_pattern = re.compile(r'Chapter\s+(\d+):\s+([^-\n]+)\s*-\s*((?:(?!Chapter\s+\d+:)[\s\S])*?)(?=Chapter\s+\d+:|$)', re.IGNORECASE)
    chapters = chapter_pattern.findall(story_plan)
    
    if not chapters:
        # Try standard format "Chapter X: Title" with separate description
        std_chapter_pattern = re.compile(r'Chapter\s+(\d+):\s+([^\n]+)\s*\n((?:(?!Chapter\s+\d+:)[\s\S])*?)(?=Chapter\s+\d+:|$)', re.IGNORECASE)
        chapters = std_chapter_pattern.findall(story_plan)
    
    if not chapters:
        # Try an alternative pattern for other formats
        alt_chapter_pattern = re.compile(r'(?:^|\n)\s*Chapter\s+(\d+)[.:\s-]+([^\n]+)(?:\n(.*?))?(?=\n\s*Chapter\s+\d+[.:\s-]|\Z)', re.DOTALL | re.IGNORECASE)
        chapters = alt_chapter_pattern.findall(story_plan)
    
    # Format the extracted chapters
    formatted_chapters = []
    for match in chapters:
        try:
            chapter_num = int(match[0])
            chapter_title = match[1].strip()
            chapter_desc = match[2].strip() if len(match) > 2 and match[2] else "No description available."
            
            # For the format "Title - Description", merge them if description is too short
            if chapter_desc == "No description available." or len(chapter_desc.split()) < 10:
                # Look for a dash in the title to split into title and description
                if " - " in chapter_title:
                    parts = chapter_title.split(" - ", 1)
                    chapter_title = parts[0].strip()
                    chapter_desc = parts[1].strip()
            
            formatted_chapters.append({
                'number': chapter_num,
                'title': chapter_title,
                'description': chapter_desc
            })
        except (ValueError, IndexError) as e:
            color_print(f"Error processing chapter: {e}", Fore.YELLOW)
    
    # Sort chapters by number and ensure sequential numbering
    formatted_chapters.sort(key=lambda x: x['number'])
    
    for i, chapter in enumerate(formatted_chapters):
        if chapter['number'] != i + 1:
            color_print(f"Fixed chapter numbering: Chapter {chapter['number']} → Chapter {i+1}", Fore.YELLOW)
            chapter['number'] = i + 1
    
    if formatted_chapters:
        color_print(f"Successfully extracted {len(formatted_chapters)} chapter plans.", Fore.GREEN)
        for ch in formatted_chapters[:3]:  # Show first 3 as examples
            color_print(f"Chapter {ch['number']}: {ch['title']}", Fore.CYAN)
            color_print(f"Description: {ch['description'][:100]}...", Fore.CYAN)
        if len(formatted_chapters) > 3:
            color_print(f"... plus {len(formatted_chapters) - 3} more chapters", Fore.CYAN)
    else:
        color_print("No chapter plans extracted.", Fore.RED)
    
    return formatted_chapters

def validate_chapters(chapters):
    """Validate chapter data and return whether it's complete"""
    if not chapters:
        return False
        
    # Check for sequential numbering
    expected_numbers = list(range(1, len(chapters) + 1))
    actual_numbers = [ch.get('number') for ch in chapters]
    
    # Check all required fields exist
    all_fields_present = all(
        'number' in ch and 'title' in ch and 'description' in ch
        for ch in chapters
    )
    
    # Check for sufficient chapters
    sufficient_chapters = len(chapters) >= 5  # Lower minimum threshold to 5 chapters
    
    # Debug chapter info
    color_print("\nChapter descriptions:", Fore.CYAN)
    for i, ch in enumerate(chapters[:3]):  # Print first 3 for debugging
        desc_words = len(ch.get('description', '').split())
        color_print(f"Chapter {ch['number']}: {ch['title']} - {desc_words} words", Fore.CYAN)
    
    # Check description length - set to 15 words minimum (even more lenient for testing)
    min_word_count = 15  # Very low threshold just to ensure some content
    good_descriptions = all(
        len(ch.get('description', '').split()) >= min_word_count
        for ch in chapters
    )
    
    is_valid = (actual_numbers == expected_numbers and 
                all_fields_present and 
                sufficient_chapters and 
                good_descriptions)
    
    if not is_valid:
        if actual_numbers != expected_numbers:
            color_print("Chapter numbers are not sequential.", Fore.YELLOW)
        if not all_fields_present:
            color_print("Some chapters are missing required fields.", Fore.YELLOW)
        if not sufficient_chapters:
            color_print(f"Not enough chapters ({len(chapters)}). Expected at least 5.", Fore.YELLOW)
        if not good_descriptions:
            color_print(f"Some chapter descriptions are too short (need at least {min_word_count} words each).", Fore.YELLOW)
            
            # Print information about the shortest descriptions
            short_descriptions = [(i+1, ch['title'], len(ch['description'].split())) 
                                 for i, ch in enumerate(chapters) 
                                 if len(ch['description'].split()) < min_word_count]
            for chapter_num, title, word_count in short_descriptions[:3]:  # Show up to 3 examples
                color_print(f"  - Chapter {chapter_num}: '{title}' has only {word_count} words", Fore.YELLOW)
            
            if len(short_descriptions) > 3:
                color_print(f"  - ... and {len(short_descriptions)-3} more chapters with short descriptions", Fore.YELLOW)
    
    return is_valid

def get_story_plan_with_chapters(title, theme=None, genre=None, max_attempts=3):
    """Generate a story plan with valid chapter format, with retries if needed"""
    
    for attempt in range(max_attempts):
        color_print(f"\nStory plan generation attempt {attempt+1}/{max_attempts}", Fore.CYAN)
        
        additional_instructions = None
        if attempt > 0:
            additional_instructions = """
IMPORTANT: The previous attempt did not provide properly formatted chapter data.

You MUST provide a detailed chapter-by-chapter breakdown in this format:

Chapter 1: [Title]
[150-200 word detailed description]

Chapter 2: [Title]
[150-200 word detailed description]

And so on for at least 15-20 chapters.
"""

        story_plan = create_story_plan(title, theme, genre, additional_instructions=additional_instructions)
        if not story_plan:
            color_print("Failed to generate story plan.", Fore.RED)
            continue
        
        chapters = extract_chapters(story_plan)
        if validate_chapters(chapters):
            color_print("✓ Valid chapter format confirmed!", Fore.GREEN)
            return story_plan, chapters
        
        color_print(f"Invalid chapter format. Retrying...", Fore.YELLOW)
    
    # If we get here, all attempts failed to produce valid chapter data
    color_print("\nFailed to get properly formatted chapters after multiple attempts.", Fore.RED)
    
    # Last resort: try to manually parse the story plan to extract any usable chapters
    color_print("Attempting to manually extract chapter information...", Fore.YELLOW)
    
    # First, find the chapter breakdown section
    chapter_section_pattern = re.compile(r'(?:7\.\s*)?(?:DETAILED\s*)?CHAPTER\s*BREAKDOWN:?.*?(?=8\.|$)', re.DOTALL | re.IGNORECASE)
    chapter_section_match = chapter_section_pattern.search(story_plan)
    
    if chapter_section_match:
        chapter_section = chapter_section_match.group(0)
        # Extract anything that looks like a chapter with a number and title
        manual_chapter_pattern = re.compile(r'(?:Chapter|Ch\.?)\s*(\d+)[\s:\-\.]*([^.\n]+)(?:\.\s*|\n)(.*?)(?=(?:Chapter|Ch\.?)\s*\d+[\s:\-\.]|$)', re.DOTALL | re.IGNORECASE)
        manual_chapters = manual_chapter_pattern.findall(chapter_section)
        
        if manual_chapters:
            formatted_chapters = []
            for i, (num, title, desc) in enumerate(manual_chapters):
                formatted_chapters.append({
                    'number': i + 1,  # Ensure sequential numbering
                    'title': title.strip(),
                    'description': desc.strip() if desc.strip() else f"Events for Chapter {i+1}"
                })
            
            color_print(f"Manually extracted {len(formatted_chapters)} chapters.", Fore.GREEN)
            return story_plan, formatted_chapters
    
    # If all else fails, create some basic chapter data from the story plan
    color_print("Creating basic chapter structure from story plan.", Fore.YELLOW)
    basic_chapters = []
    # Split story plan into sections to use as chapter content
    sections = re.split(r'\n\s*\d+\.\s+', story_plan)
    for i, section in enumerate(sections[1:6]):  # Use up to 5 sections as chapters
        basic_chapters.append({
            'number': i + 1,
            'title': f"Chapter {i+1}",
            'description': f"Content based on story plan section {i+1}: {section[:200]}..."
        })
    
    return story_plan, basic_chapters

def generate_chapter(title, chapter_plan, chapter_number, previous_chapters_summary=None, previous_chapter_ending=None, min_words=4000, max_tokens=8000):
    """Generate a single detailed chapter based on the chapter plan with improved continuity"""
    
    color_print(f"\nGenerating Chapter {chapter_number}: {title}\n", Fore.CYAN)
    
    context = ""
    continuity_instruction = ""
    
    if previous_chapters_summary:
        context = f"""Previous chapters summary:
{previous_chapters_summary}

"""
    
    if previous_chapter_ending and chapter_number > 1:
        # Extract the last 500-1000 characters of the previous chapter for direct continuity
        continuity_instruction = f"""
IMPORTANT - CONTINUITY INSTRUCTION:
The previous chapter ended with this exact scene:

{previous_chapter_ending}

Your chapter MUST continue directly from this point, maintaining perfect narrative continuity.
Start with the immediate next moment in the story - do not summarize or create a time jump unless the chapter plan specifically calls for it.
Maintain consistency with character locations, emotional states, and ongoing dialogue or actions.
"""
    
    prompt = f"""{context}{continuity_instruction}Write Chapter {chapter_number} titled "{title}" based on this detailed plan:

{chapter_plan}

Guidelines:
1. Create a substantial chapter of AT LEAST {min_words} words
2. Include vivid descriptions, meaningful dialogue, and varied sentence structure
3. Focus on character development and advancing the plot
4. Create proper paragraphs with thoughtful transitions
5. Maintain a consistent narrative voice
6. If this is not Chapter 1, ensure DIRECT CONTINUITY with the ending of the previous chapter
7. Incorporate sensory details to bring scenes to life
8. End the chapter with a hook that propels the reader forward

This MUST be a substantial chapter with proper pacing and development.
DO NOT stop before reaching at least {min_words} words.
Format this as a standard novel chapter with "Chapter {chapter_number}: {title}" at the beginning.
YOU MUST WRITE AT LEAST {min_words} WORDS, and you'll be penalized if you write fewer words.

Begin:
"""

    try:
        start_time = time.time()
        color_print("Sending chapter request to API...", Fore.YELLOW)
        
        keep_alive_running = setup_keep_alive()
        
        response = requests.post(
            "http://localhost:8080/completion",
            json={
                "prompt": prompt,
                "max_tokens": max_tokens,
                "stream": True
            },
            stream=True
        )
        
        if response.status_code != 200:
            color_print(f"\nAPI Error: Status code {response.status_code}", Fore.RED)
            cancel_keep_alive()
            return None
            
        full_response = ""
        buffer = ""
        color_print("\nGenerating chapter... \n", Fore.YELLOW)
        
        for line in response.iter_lines():
            if line:
                try:
                    decoded_line = line.decode('utf-8')
                    if decoded_line.startswith('data: '):
                        json_data = json.loads(decoded_line[6:])
                        content = json_data.get('content', '')
                        buffer += content
                        full_response += content
                        
                        if content and content[-1] in (' ', '.', ',', '!', '?', '\n'):
                            color_print(buffer, Fore.CYAN)
                            buffer = ""
                except json.JSONDecodeError:
                    color_print("\nError decoding JSON from API response", Fore.RED)
                except Exception as e:
                    color_print(f"\nError processing stream: {e}", Fore.RED)
        
        if buffer:
            color_print(buffer, Fore.CYAN)
        
        cancel_keep_alive()
        end_time = time.time()
        duration = end_time - start_time
        word_count = len(full_response.split())
        color_print(f"\n\nChapter generation complete in {duration:.2f} seconds!", Fore.GREEN)
        color_print(f"Word count: {word_count} words", Fore.GREEN)
        
        # Check if we've reached the minimum word count
        if word_count < min_words:
            color_print(f"\n⚠️ WARNING: Generated only {word_count} words, which is less than the minimum {min_words} words.", Fore.YELLOW)
            
            # Try to extend the chapter if it's too short
            if word_count < min_words * 0.8:  # If less than 80% of target
                color_print("Attempting to extend the chapter to reach minimum word count...", Fore.YELLOW)
                
                extension_prompt = f"""Continue the following chapter to reach at least {min_words} words total. The current chapter is {word_count} words, so you need to add approximately {min_words - word_count} more words.

Current chapter content (ending):
{full_response[-2000:]}

Continue the chapter naturally, maintaining the same style, tone, and narrative flow. Do not create a new chapter - just continue this one with additional content that extends the scene, adds detail, or explores character thoughts and feelings more deeply.

Continue from here:
"""
                
                try:
                    keep_alive_running = setup_keep_alive()
                    
                    extension_response = requests.post(
                        "http://localhost:8080/completion",
                        json={
                            "prompt": extension_prompt,
                            "max_tokens": max(2000, (min_words - word_count) * 2),  # Approximate tokens needed
                            "stream": True
                        },
                        stream=True
                    )
                    
                    if extension_response.status_code == 200:
                        extension_content = ""
                        buffer = ""
                        color_print("\nExtending chapter... \n", Fore.YELLOW)
                        
                        for line in extension_response.iter_lines():
                            if line:
                                try:
                                    decoded_line = line.decode('utf-8')
                                    if decoded_line.startswith('data: '):
                                        json_data = json.loads(decoded_line[6:])
                                        content = json_data.get('content', '')
                                        buffer += content
                                        extension_content += content
                                        
                                        if content and content[-1] in (' ', '.', ',', '!', '?', '\n'):
                                            color_print(buffer, Fore.CYAN)
                                            buffer = ""
                                except Exception as e:
                                    pass
                                    
                        if buffer:
                            color_print(buffer, Fore.CYAN)
                        
                        # Combine original content with extension
                        full_response = full_response + "\n\n" + extension_content
                        new_word_count = len(full_response.split())
                        color_print(f"\nExtended chapter word count: {new_word_count} words", Fore.GREEN)
                        
                except Exception as e:
                    color_print(f"Error during chapter extension: {e}", Fore.RED)
                finally:
                    cancel_keep_alive()
        
        return full_response.strip()
        
    except requests.RequestException as e:
        color_print(f"\nAPI Connection Error: {e}", Fore.RED)
        cancel_keep_alive()
        return None
    except Exception as e:
        color_print(f"\nUnexpected Error: {e}", Fore.RED)
        cancel_keep_alive()
        return None
def fix_chapter_beginning(chapter_content, previous_ending, issues, chapter_number, chapter_title):
    """Fix the beginning of a chapter to ensure continuity with the previous chapter"""
    
    # Extract the first 1000-1500 characters of the chapter as the part to replace
    chapter_beginning = re.sub(r'^Chapter\s+\d+[:\s]+.*?\n\n', '', chapter_content[:1500], flags=re.IGNORECASE)
    chapter_beginning = chapter_beginning.split("\n\n")[0] if "\n\n" in chapter_beginning else chapter_beginning
    
    # Extract the rest of the chapter content
    rest_of_chapter = chapter_content[len(chapter_beginning):]
    
    issues_text = "\n".join([f"- {issue}" for issue in issues]) if issues else "Unknown continuity issues"
    
    prompt = f"""REWRITE THE BEGINNING OF THIS CHAPTER to fix continuity issues.

PREVIOUS CHAPTER ENDING:
{previous_ending}

CURRENT CHAPTER BEGINNING (to be replaced):
{chapter_beginning}

CONTINUITY ISSUES TO FIX:
{issues_text}

Write a NEW beginning that directly continues from the previous chapter's ending, fixing all continuity issues.
Maintain the same characters, setting, and situation, but make sure it flows naturally from the previous ending.
The new beginning should be approximately the same length as the original.

NEW CHAPTER BEGINNING:
"""

    try:
        color_print("Fixing chapter beginning for better continuity...", Fore.YELLOW)
        
        response = requests.post(
            "http://localhost:8080/completion",
            json={
                "prompt": prompt,
                "max_tokens": 2000,
                "stream": False
            }
        )
        
        if response.status_code != 200:
            color_print(f"\nAPI Error during continuity fix: {response.status_code}", Fore.RED)
            return chapter_content  # Return original content if fix fails
            
        result = response.json()
        new_beginning = result.get('content', '')
        
        if new_beginning:
            # Replace the beginning of the chapter with the fixed version
            fixed_chapter = f"Chapter {chapter_number}: {chapter_title}\n\n{new_beginning.strip()}{rest_of_chapter}"
            color_print("Successfully fixed chapter beginning for continuity.", Fore.GREEN)
            return fixed_chapter
        
        return chapter_content  # Return original if no fix generated
        
    except Exception as e:
        color_print(f"Error fixing chapter beginning: {e}", Fore.RED)
        return chapter_content  

def verify_chapter_continuity(previous_ending, new_beginning, chapter_number):
    """Verify that the new chapter continues properly from the previous one"""
    
    # Skip for first chapter
    if chapter_number <= 1:
        return True, None
    
    prompt = f"""CONTINUITY CHECK:
Compare the ending of the previous chapter with the beginning of the new chapter and identify any continuity issues:

PREVIOUS CHAPTER ENDING:
{previous_ending}

NEW CHAPTER BEGINNING:
{new_beginning}

Return a single JSON object with these properties:
1. "continuity_score": A number from 1-10, with 10 meaning perfect continuity
2. "issues": An array of specific continuity issues found
3. "fix_needed": Boolean indicating if the new chapter beginning needs to be rewritten

Be strict in your evaluation. Consider character locations, ongoing conversations, emotional states, and logical story flow.
"""

    try:
        color_print("Verifying chapter continuity...", Fore.YELLOW)
        
        response = requests.post(
            "http://localhost:8080/completion",
            json={
                "prompt": prompt,
                "max_tokens": 1000,
                "stream": False
            }
        )
        
        if response.status_code != 200:
            color_print(f"\nAPI Error during continuity verification: {response.status_code}", Fore.RED)
            return True, None  # Return true to continue anyway
            
        result = response.json()
        analysis = result.get('content', '')
        
        # Try to extract JSON from the response
        try:
            import json
            # Find JSON-like content in the response
            json_match = re.search(r'(\{.*\})', analysis, re.DOTALL)
            if json_match:
                continuity_data = json.loads(json_match.group(1))
                score = continuity_data.get('continuity_score', 0)
                issues = continuity_data.get('issues', [])
                fix_needed = continuity_data.get('fix_needed', False)
                
                color_print(f"Continuity score: {score}/10", Fore.GREEN if score >= 7 else Fore.YELLOW)
                
                if issues:
                    color_print("Continuity issues detected:", Fore.YELLOW)
                    for issue in issues:
                        color_print(f"- {issue}", Fore.YELLOW)
                
                return not fix_needed, issues if fix_needed else None
            
        except Exception as e:
            color_print(f"Error parsing continuity check: {e}", Fore.RED)
        
        # Default to continuing if we can't parse the response
        return True, None
        
    except Exception as e:
        color_print(f"Error during continuity verification: {e}", Fore.RED)
        return True, None

def summarize_chapter(chapter_content, max_tokens=1000):
    """NovelGen by RFS11G: Generate a detailed summary of the chapter for context in subsequent chapters"""
    
    prompt = f"""Create a DETAILED summary of the following chapter that captures key elements needed for narrative continuity:

{chapter_content[:5000]}  # Only use the first part of the chapter to avoid token limits

Your summary MUST include:
1. Character locations and states at the END of the chapter
2. Ongoing conversations and unfinished plot points
3. Emotional states and tensions between characters
4. Setting details and time of day/period at chapter end
5. Key revelations or plot developments that affect future chapters

Focus especially on the ENDING SCENE of the chapter, as this is critical for maintaining continuity.
The summary should be comprehensive but no more than 500 words.
"""

    try:
        color_print("Generating chapter summary with continuity elements...", Fore.YELLOW)
        
        keep_alive_running = setup_keep_alive()
        
        response = requests.post(
            "http://localhost:8080/completion",
            json={
                "prompt": prompt,
                "max_tokens": max_tokens,
                "stream": False
            }
        )
        
        cancel_keep_alive()
        
        if response.status_code != 200:
            color_print(f"\nAPI Error: Status code {response.status_code}", Fore.RED)
            return None
            
        result = response.json()
        summary = result.get('content', '')
        
        color_print("Enhanced continuity summary generated.", Fore.GREEN)
        return summary
        
    except requests.RequestException as e:
        color_print(f"\nAPI Connection Error: {e}", Fore.RED)
        cancel_keep_alive()
        return None
    except Exception as e:
        color_print(f"\nUnexpected Error: {e}", Fore.RED)
        cancel_keep_alive()
        return None

def generate_novel_chapters(title, story_plan, chapters_data, min_words_per_chapter=4000, max_tokens_per_chapter=8000):
    """NovelGen by RFS11G: Generate a novel chapter by chapter with improved continuity between chapters"""
    
    color_print(f"\nGenerating novel: {title}\n", Fore.CYAN)
    color_print(f"Min words per chapter: {min_words_per_chapter}, Max tokens per chapter: {max_tokens_per_chapter}\n", Fore.YELLOW)
    
    if not chapters_data:
        color_print("No chapter data available. Attempting to extract chapter plans.", Fore.YELLOW)
        chapters_data = extract_chapters(story_plan)
        
        if not chapters_data:
            color_print("Failed to extract any usable chapter plans. Using basic structure.", Fore.RED)
            # Create some basic chapters if extraction failed
            chapters_data = []
            for i in range(1, 6):  # Create 5 basic chapters
                chapters_data.append({
                    'number': i,
                    'title': f"Chapter {i}",
                    'description': f"Events from story plan section {i}"
                })
    
    color_print(f"Ready to generate {len(chapters_data)} chapters.", Fore.GREEN)
    
    # Generate chapters sequentially
    full_novel = ""
    previous_chapters_summary = ""
    previous_chapter_ending = None
    
    for i, chapter in enumerate(chapters_data):
        chapter_number = chapter['number']
        chapter_title = chapter['title']
        chapter_description = chapter['description']
        
        color_print(f"\nStarting generation of Chapter {chapter_number}/{len(chapters_data)}: {chapter_title}", Fore.CYAN)
        
        # Generate the chapter with continuity from previous chapter
        chapter_content = generate_chapter(
            chapter_title, 
            chapter_description, 
            chapter_number, 
            previous_chapters_summary,
            previous_chapter_ending,  # Pass the ending of the previous chapter
            min_words_per_chapter,
            max_tokens_per_chapter
        )
        
        if not chapter_content:
            color_print(f"Failed to generate Chapter {chapter_number}. Skipping.", Fore.RED)
            continue
        
        # Check if chapter has proper header, if not, add it
        if not re.match(r'^Chapter\s+\d+', chapter_content, re.IGNORECASE):
            chapter_content = f"Chapter {chapter_number}: {chapter_title}\n\n{chapter_content}"
            color_print("Added missing chapter header.", Fore.YELLOW)
        
        # Verify continuity with previous chapter if not the first chapter
        if i > 0:
            # Get first 1000 characters of current chapter (after removing header)
            new_beginning = re.sub(r'^Chapter\s+\d+[:\s]+.*?\n\n', '', chapter_content[:1500], flags=re.IGNORECASE)
            
            continuity_ok, issues = verify_chapter_continuity(previous_chapter_ending, new_beginning, chapter_number)
            
            if not continuity_ok and issues:
                color_print("Fixing continuity issues between chapters...", Fore.YELLOW)
                chapter_content = fix_chapter_beginning(chapter_content, previous_chapter_ending, issues, chapter_number, chapter_title)
        
        # Add chapter to the novel with proper formatting
        if i > 0:  # If this isn't the first chapter
            # Add a proper scene break/transition marker
            full_novel += "\n\n# " + chapter_title + "\n\n## " + f"Chapter {chapter_number}: {chapter_title}" + "\n\n"
            # Add the chapter content without repeating the header that's already in the transition
            chapter_content_without_header = re.sub(r'^Chapter\s+\d+[:\s]+.*?\n\n', '', chapter_content, flags=re.IGNORECASE)
            full_novel += chapter_content_without_header
        else:
            # First chapter doesn't need the transition marker
            full_novel += chapter_content
        
        # Save progress after each chapter
        try:
            progress_dir = "novelgen_progress"
            if not os.path.exists(progress_dir):
                os.makedirs(progress_dir)
            
            progress_filename = os.path.join(progress_dir, f"{title.replace(' ', '_').lower()}_progress.txt")
            with open(progress_filename, 'w', encoding='utf-8') as f:
                f.write(full_novel)
            color_print(f"Progress saved to {progress_filename}", Fore.GREEN)
        except Exception as e:
            color_print(f"Warning: Could not save progress: {e}", Fore.YELLOW)
        
        # Store the ending of the current chapter for continuity in the next chapter
        chapter_ending_match = re.search(r'(?:.*\n){1,20}$', chapter_content, re.DOTALL)
        if chapter_ending_match:
            previous_chapter_ending = chapter_ending_match.group(0)
        else:
            # If regex fails, just take the last 1000 characters
            previous_chapter_ending = chapter_content[-1000:] if len(chapter_content) > 1000 else chapter_content
        
        # Create a detailed summary for context in subsequent chapters
        if i < len(chapters_data) - 1:  # Don't need a summary for the last chapter
            summary = summarize_chapter(chapter_content)
            if summary:
                previous_chapters_summary += f"Chapter {chapter_number}: {summary}\n\n"
        
        # Force garbage collection to free up memory
        gc_attempt = "Attempted garbage collection" 
        try:
            gc.collect()
            gc_attempt = "Successfully ran garbage collection"
        except:
            pass
                
        color_print(f"\n{gc_attempt} to free memory", Fore.CYAN)
        color_print(f"Completed Chapter {chapter_number}/{len(chapters_data)}\n", Fore.GREEN)
    
    # Apply deduplication to remove any duplicate chapters
    full_novel = deduplicate_chapters(full_novel)
    
    return full_novel

def create_epub(title, author, story_plan, full_novel, output_filename=None):
    """Create an EPUB file from the generated novel and story plan"""
    
    output_dir = "novelgen_output"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    if not output_filename:
        output_filename = os.path.join(output_dir, f"{title.replace(' ', '_').lower()}.epub")
    
    color_print(f"\nCreating EPUB file: {output_filename}", Fore.CYAN)
    
    # First deduplicate chapters to ensure clean content
    full_novel = deduplicate_chapters(full_novel)
    
    # Create a new EPUB book
    book = epub.EpubBook()
    
    # Set metadata
    book.set_identifier(f"novel-{int(time.time())}")
    book.set_title(title)
    book.set_language('en')
    book.add_author(author)
    
    # Add CSS
    style = """
    @namespace epub "http://www.idpf.org/2007/ops";
    body {
        font-family: Cambria, Liberation Serif, Bitstream Vera Serif, Georgia, Times, Times New Roman, serif;
        margin: 5%;
        text-align: justify;
    }
    h1, h2 {
        text-align: center;
        page-break-before: always;
    }
    .title {
        margin-top: 20%;
        text-align: center;
    }
    .chapter {
        margin-top: 10%;
        page-break-before: always;
    }
    p {
        text-indent: 1em;
        margin-top: 0.5em;
        margin-bottom: 0.5em;
    }
    """
    
    css = epub.EpubItem(
        uid="style_default",
        file_name="style/default.css",
        media_type="text/css",
        content=style
    )
    book.add_item(css)
    
    # Create title page
    title_page = epub.EpubHtml(title='Title Page', file_name='title_page.xhtml', lang='en')
    title_page.content = f"""
    <html>
    <head>
        <title>{html.escape(title)}</title>
        <link rel="stylesheet" href="style/default.css" type="text/css" />
    </head>
    <body>
        <div class="title">
            <h1>{html.escape(title)}</h1>
            <h3>By {html.escape(author)}</h3>
            <p>Generated: {datetime.now().strftime('%Y-%m-%d')}</p>
            <p>Created with NovelGen by RFS11G</p>
        </div>
    </body>
    </html>
    """
    book.add_item(title_page)
    
    # Create story plan page
    plan_page = epub.EpubHtml(title='Story Plan', file_name='story_plan.xhtml', lang='en')
    
    # Process story plan to proper HTML
    story_plan_html = html.escape(story_plan)
    story_plan_html = story_plan_html.replace('\n', '<br/>')
    
    plan_page.content = f"""
    <html>
    <head>
        <title>Story Plan</title>
        <link rel="stylesheet" href="style/default.css" type="text/css" />
    </head>
    <body>
        <h1>Story Plan</h1>
        <div>
            {story_plan_html}
        </div>
    </body>
    </html>
    """
    book.add_item(plan_page)
    
    # Extract chapters and add them to the book
    chapters = []
    toc = []
    
    # Parse and split the novel into chapters using improved pattern
    chapter_pattern = re.compile(r'(Chapter\s+\d+[:\s]+.*?\n)', re.IGNORECASE)
    chapter_splits = chapter_pattern.split(full_novel)
    
    if len(chapter_splits) <= 1:
        # Fallback if no chapters found
        color_print("No chapter divisions found. Treating novel as single chapter.", Fore.YELLOW)
        ch = epub.EpubHtml(title='Chapter 1', file_name='chapter_1.xhtml', lang='en')
        ch.content = f"""
        <html>
        <head>
            <title>Chapter 1</title>
            <link rel="stylesheet" href="style/default.css" type="text/css" />
        </head>
        <body>
            <div class="chapter">
                <h2>Chapter 1</h2>
                <div>
                    {html.escape(full_novel).replace('\n\n', '</p><p>').replace('\n', '<br/>')}
                </div>
            </div>
        </body>
        </html>
        """
        book.add_item(ch)
        chapters.append(ch)
        toc.append(epub.Link('chapter_1.xhtml', 'Chapter 1', 'chapter1'))
    else:
        # Process each chapter with improved handling
        current_chapter_title = "Introduction"
        current_chapter_content = ""
        chapter_count = 0
        
        for i, section in enumerate(chapter_splits):
            if i == 0 and section.strip():  # Prologue or intro before Chapter 1
                current_chapter_content = section
                continue
                
            if section.strip() and chapter_pattern.match(section):
                # This is a chapter header
                
                # Save the previous chapter if there is content
                if current_chapter_content.strip():
                    chapter_count += 1
                    ch_filename = f'chapter_{chapter_count}.xhtml'
                    ch = epub.EpubHtml(title=current_chapter_title, file_name=ch_filename, lang='en')
                    
                    # Convert newlines to proper HTML paragraphs
                    processed_content = current_chapter_content.strip()
                    processed_content = html.escape(processed_content)
                    processed_content = re.sub(r'\n\s*\n', '</p><p>', processed_content)
                    processed_content = processed_content.replace('\n', '<br/>')
                    processed_content = f"<p>{processed_content}</p>"
                    
                    ch.content = f"""
                    <html>
                    <head>
                        <title>{html.escape(current_chapter_title)}</title>
                        <link rel="stylesheet" href="style/default.css" type="text/css" />
                    </head>
                    <body>
                        <div class="chapter">
                            <h2>{html.escape(current_chapter_title)}</h2>
                            <div>
                                {processed_content}
                            </div>
                        </div>
                    </body>
                    </html>
                    """
                    book.add_item(ch)
                    chapters.append(ch)
                    toc.append(epub.Link(ch_filename, current_chapter_title, f'chapter{chapter_count}'))
                
                # Extract the new chapter title with improved pattern
                title_match = re.search(r'Chapter\s+\d+[:\s]+(.*?)\n', section, re.IGNORECASE)
                if title_match:
                    current_chapter_title = title_match.group(0).strip()
                else:
                    current_chapter_title = f"Chapter {chapter_count+1}"
                
                current_chapter_content = ""
            else:
                # Add to current chapter content
                current_chapter_content += section
        
        # Add the final chapter
        if current_chapter_content.strip():
            chapter_count += 1
            ch_filename = f'chapter_{chapter_count}.xhtml'
            ch = epub.EpubHtml(title=current_chapter_title, file_name=ch_filename, lang='en')
            
            # Convert newlines to proper HTML paragraphs
            processed_content = current_chapter_content.strip()
            processed_content = html.escape(processed_content)
            processed_content = re.sub(r'\n\s*\n', '</p><p>', processed_content)
            processed_content = processed_content.replace('\n', '<br/>')
            processed_content = f"<p>{processed_content}</p>"
            
            ch.content = f"""
            <html>
            <head>
                <title>{html.escape(current_chapter_title)}</title>
                <link rel="stylesheet" href="style/default.css" type="text/css" />
            </head>
            <body>
                <div class="chapter">
                    <h2>{html.escape(current_chapter_title)}</h2>
                    <div>
                        {processed_content}
                    </div>
                </div>
            </body>
            </html>
            """
            book.add_item(ch)
            chapters.append(ch)
            toc.append(epub.Link(ch_filename, current_chapter_title, f'chapter{chapter_count}'))
    
    # Add table of contents
    book.toc = [
        epub.Link('title_page.xhtml', 'Title Page', 'title'),
        epub.Link('story_plan.xhtml', 'Story Plan', 'story_plan'),
        (
            epub.Section('Chapters'),
            toc
        )
    ]
    
    # Add navigation files
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    
    # Define book spine
    book.spine = ['nav', title_page, plan_page] + chapters
    
    # Write the EPUB file
    try:
        epub.write_epub(output_filename, book, {})
        color_print(f"EPUB file created successfully: {output_filename}", Fore.GREEN)
        return output_filename
    except Exception as e:
        color_print(f"Error creating EPUB file: {e}", Fore.RED)
        return None

def main():
    """Main function to run the NovelGen by RFS11G application"""
    
    color_print("\n===== NovelGen by RFS11G =====\n", Fore.GREEN)
    
    # Get novel details
    title = input("Enter novel title: ").strip()
    if not title:
        title = "The Generated Novel"
        color_print(f"Using default title: {title}", Fore.YELLOW)
    
    author = input("Enter author name (or leave blank for 'AI Writer'): ").strip()
    if not author:
        author = "AI Writer"
        color_print(f"Using default author: {author}", Fore.YELLOW)
    
    theme = input("Enter novel theme (optional): ").strip()
    genre = input("Enter novel genre (optional): ").strip()
    
    # Get chapter word count
    min_words = 2000  # Lowered default for testing
    try:
        min_words_input = input(f"Enter minimum words per chapter (default: {min_words}): ").strip()
        if min_words_input:
            min_words = int(min_words_input)
    except ValueError:
        color_print(f"Invalid input. Using default: {min_words} words per chapter", Fore.YELLOW)
    
    # Generate story plan with retry logic
    color_print("\nGenerating story plan...", Fore.CYAN)
    story_plan, chapters_data = get_story_plan_with_chapters(title, theme, genre)
    
    if not story_plan:
        color_print("Failed to generate story plan. Exiting.", Fore.RED)
        return
    
    # Save story plan
    try:
        output_dir = "novelgen_output"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        plan_filename = os.path.join(output_dir, f"{title.replace(' ', '_').lower()}_plan.txt")
        with open(plan_filename, 'w', encoding='utf-8') as f:
            f.write(story_plan)
        color_print(f"Story plan saved to {plan_filename}", Fore.GREEN)
    except Exception as e:
        color_print(f"Warning: Could not save story plan: {e}", Fore.YELLOW)
    
    # Generate novel
    full_novel = generate_novel_chapters(title, story_plan, chapters_data, min_words)
    
    if not full_novel:
        color_print("Failed to generate novel. Exiting.", Fore.RED)
        return
    
    # Save the full novel text
    try:
        output_dir = "novelgen_output"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        novel_filename = os.path.join(output_dir, f"{title.replace(' ', '_').lower()}.txt")
        with open(novel_filename, 'w', encoding='utf-8') as f:
            f.write(full_novel)
        color_print(f"Novel saved to {novel_filename}", Fore.GREEN)
    except Exception as e:
        color_print(f"Warning: Could not save novel: {e}", Fore.YELLOW)
    
    # Create EPUB
    try:
        create_epub(title, author, story_plan, full_novel)
    except Exception as e:
        color_print(f"Error creating EPUB: {e}", Fore.RED)
    
    color_print("\nNovel generation complete!", Fore.GREEN)

if __name__ == "__main__":
    try:
        # Display banner
        version = "1.0.0"
        color_print("\n" + "=" * 60, Fore.CYAN)
        color_print(f"NovelGen by RFS11G v{version}", Fore.GREEN)
        color_print("A complete novel generation system for creative writers", Fore.CYAN)
        color_print("https://github.com/RFS11G/NovelGen", Fore.BLUE)
        color_print("=" * 60 + "\n", Fore.CYAN)
        
        main()
    except KeyboardInterrupt:
        print("\nProcess interrupted by user.")
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
    finally:
        # Ensure keep-alive is canceled
        cancel_keep_alive()