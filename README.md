# NovelGen

A Python-based novel generation tool that uses local AI models to create complete fictional novels with proper narrative structure, chapter planning, and consistent storytelling.

## Features

- Generates comprehensive story plans with detailed character profiles, narrative structure, and theme exploration
- Creates chapter-by-chapter outlines with titles and descriptions
- Produces fully-written chapters with proper narrative flow
- Maintains continuity between chapters using AI-powered verification
- Exports to both text and EPUB formats
- Includes deduplication to prevent repeated content
- Implements a keep-alive function to prevent system sleep during long generation tasks

## Requirements

- Python 3.6+
- A local AI inference server running on http://localhost:8080/completion
- Required Python packages (see requirements.txt)

## Installation

1. Clone this repository:
```bash
git clone https://github.com/yourusername/NovelGen.git
cd NovelGen
```

2. Install the required packages:
```bash
pip install -r requirements.txt
```

## Usage

Run the main script:
```bash
python novelgen.py
```

You'll be prompted to enter:
- Novel title
- Author name (optional)
- Theme (optional)
- Genre (optional)
- Minimum words per chapter

The script will generate:
1. A detailed story plan
2. Chapter-by-chapter outlines
3. Complete chapters with proper narrative flow
4. A full novel in both .txt and .epub formats

## How It Works

1. **Story Plan Generation**: The script creates a detailed story plan including premise, characters, narrative structure, and chapter breakdowns.

2. **Chapter Extraction**: It extracts individual chapter plans from the overall story plan.

3. **Chapter Generation**: Each chapter is generated sequentially, with special attention to maintaining continuity.

4. **Continuity Verification**: AI-powered checks ensure proper narrative flow between chapters.

5. **Deduplication**: Removes any accidentally duplicated content.

6. **Export**: Saves the novel as both plaintext (.txt) and e-book (.epub) formats.

## File Structure

- `novelgen.py`: The main script
- `requirements.txt`: Required Python packages
- `LICENSE`: MIT License file
- `.gitignore`: Standard Python gitignore file
- `README.md`: This file

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Uses [EbookLib](https://github.com/aerkalov/ebooklib) for EPUB generation
- Built with [Colorama](https://github.com/tartley/colorama) for terminal color output
