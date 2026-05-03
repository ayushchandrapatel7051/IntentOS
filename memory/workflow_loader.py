import os
import yaml

def load_workflows(directory="memory/workflows"):
    """Load all YAML workflows from the given directory."""
    workflows = []
    if not os.path.exists(directory):
        return workflows
    
    for filename in os.listdir(directory):
        if not filename.endswith(('.yaml', '.yml')):
            continue
        filepath = os.path.join(directory, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                if isinstance(data, dict):
                    workflows.append({
                        "id": filename,
                        "name": data.get("name", "Unknown Workflow"),
                        "description": data.get("description", ""),
                        "steps": data.get("steps", []),
                        "tags": data.get("tags", []),
                        "type": "workflow"
                    })
        except Exception as e:
            print(f"[WorkflowLoader] Failed to load {filename}: {e}")
            
    return workflows
