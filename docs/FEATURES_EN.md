# 🌟 Core Features

ResonaDesktopPet is more than just a desktop ornament; it is a deep interaction system integrating multiple AI technologies.

## 1. Deep Conversational Interaction
- **Multi-Model Support**: Supports various LLMs including OpenAI (DeepSeek/GPT-4), Google Gemini, and Anthropic Claude.
- **Persistent Memory**: Features comprehensive conversation history management for coherent, context-aware dialogues.
- **Context Awareness**: The LLM accesses real-time context such as date and time to provide smarter responses.
- **OCR Context (Optional)**: Can recognize text on your screen and inject it into the prompt for enhanced environment awareness. **Warning**: This feature sends screen captures to third-party OCR services, which may lead to privacy leaks. Users use this feature at their own risk.

## 2. Full Voice Interaction
- **High-Quality TTS**: Integrates the GPT-SoVITS inference engine, supporting multiple emotional expressions for natural and vivid speech.
- **Offline STT**: Fast, privacy-focused offline speech recognition based on SenseVoice, triggerable via hotkeys.

## 3. Personalized Trigger System
- **Environmental Triggers**: Automatically responds to system temperature, hardware usage, running software, browser URLs, and more.
- **Interaction Triggers**: Configurable feedback for mouse hovering, long pressing, and multi-click combos.
- **Automated Actions**: Executes sequences of actions upon triggering, such as speaking, moving, changing transparency, or choosing random branches.

## 4. Flexible Resource Pack System
- **One-Click Swapping**: Seamlessly switch between character packs, including sprites, voice models, personality prompts, and trigger logic.
- **Highly Customizable**: Define all character behaviors through simple JSON configurations.

## 5. Comprehensive Developer Tools
- **Visual Editor**: A GUI-based trigger editor eliminates the need for manual JSON editing.
- **Simulation Environment**: A built-in sensor mocker for testing trigger logic without meeting real-world conditions.
- **Asset Pipeline**: Automated tools for processing and organizing sprites to speed up character pack creation.

## 6. Powerful MCP Extension Capabilities
- **System Control**: LLMs can execute command line instructions (`cmd`/`powershell`) via MCP tools for system-level operations (requires careful authorization).
- **File Management**: Supports reading, searching, modifying, and writing to the file system.
- **Scheduled Tasks**: LLMs can set future reminders or events (`timer_inbox`), extending beyond immediate dialogue.
- **Extensibility**: Developers can write new MCP tool scripts (Python/Node.js) to easily expand AI capabilities.

## 7. Web Service & WebSocket Interface
- **RESTful API**: Built-in FastAPI server providing standard HTTP interfaces.
- **WebSocket Real-time Stream**: Supports real-time pushing of pet status, voice data, and receiving control commands via WebSocket, facilitating Web console or third-party client development.

## 8. Physics Engine (Experimental)
- **Tangible Interaction**: Supports gravity simulation, ground collision, and wall bouncing effects.
- **Drag Inertia**: Drag and throw the pet with the mouse; it will continue to fly based on inertia and collide with screen edges.
- **Multi-Window Interaction**: (In Development) Capable of perceiving other windows and interacting physically.

---
Parts of this document were generated with the assistance of large language models, and translations were also completed by large language models. Any deviations do not represent the author's true intent.
