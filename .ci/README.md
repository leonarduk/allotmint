# AI Dev Build Setup for allotmint

## Current Status
✅ Scripts configured for your project structure  
✅ Jenkinsfile.ai updated with correct repo URL  
✅ Validation script adapted for Python + Node.js monorepo  
✅ Prompt template customized for allotmint

## Prerequisites Checklist

### On Jenkins Node
- [ ] LM Studio running with local server enabled (default: http://localhost:1234)
- [ ] Model loaded (e.g., Qwen2.5-Coder or similar code-capable model)
- [ ] Jenkins has access to: `git`, `gh` (GitHub CLI), `jq`, `curl`
- [ ] Jenkins has access to: `python3`, `pip`, `node`, `npm`
- [ ] GitHub credentials configured in Jenkins as 'github_pat'

### GitHub Setup
- [ ] Personal Access Token (PAT) with repo permissions
- [ ] Token added to Jenkins credentials as 'github_pat'
- [ ] gh CLI authenticated on Jenkins node

## Jenkins Job Configuration

1. **Create new Pipeline job** in Jenkins
2. **Name it**: `allotmint-ai-dev-build` (or similar)
3. **Pipeline section**:
   - Definition: `Pipeline script from SCM`
   - SCM: `Git`
   - Repository URL: `https://github.com/leonarduk/allotmint.git`
   - Credentials: Select your `github_pat`
   - Branch: `*/main`
   - Script Path: `.ci/Jenkinsfile.ai`
4. **Build Triggers**: Leave empty (manual only)
5. **Save**

## How to Use

### Manual Trigger
1. Go to Jenkins job
2. Click "Build Now"
3. Watch the pipeline stages:
   - Checkout code
   - Verify LM Studio is accessible
   - Create AI branch (ai-changes-XXX)
   - Call LM Studio to generate improvements
   - Run validation (tests + linting)
   - Commit changes
   - Push branch
   - Create PR

### Customizing AI Behavior

**Edit `.ci/prompt.md`** to change what the AI focuses on:
- Add specific files to modify
- Request particular improvements (performance, security, etc.)
- Set constraints

**Environment variables** in Jenkinsfile.ai:
```groovy
MODEL_NAME = 'Qwen2.5-Coder'      // Your LM Studio model
LM_API_BASE = 'http://localhost:1234'  // LM Studio URL
OUTPUT_MODE = 'patch'             // or 'file'
TARGET_PATHS = 'backend frontend/src'  // Directories to scan
```

## Troubleshooting

### "Cannot reach LM Studio"
- Ensure LM Studio is running on the Jenkins node
- Check "Local Server" is enabled in LM Studio
- Verify the port (default 1234)
- Test: `curl http://localhost:1234/v1/models`

### "gh: command not found"
Install GitHub CLI on Jenkins node:
```bash
# Debian/Ubuntu
sudo apt install gh

# RHEL/CentOS
sudo yum install gh

# Or download from: https://github.com/cli/cli/releases
```

### "Validation failed"
Check which stage failed:
- **Backend tests**: Check Python dependencies in `backend/requirements.txt`
- **Frontend tests**: Check Node modules, might need `cd frontend && npm ci`
- **Linting**: Review ESLint/Ruff errors

### "PR creation failed"
- Verify `gh auth status` on Jenkins node
- Check GitHub token has `repo` scope
- Ensure token isn't expired

### "No changes detected"
The AI might not have found anything to improve. Try:
- Being more specific in `.ci/prompt.md`
- Adjusting the temperature in `ai_apply.sh`
- Checking `.ci/ai_output.txt` to see what the model generated

## File Structure
```
.ci/
├── Jenkinsfile.ai    # AI dev pipeline
├── ai_apply.sh       # Calls LM Studio and applies changes
├── validate.sh       # Runs tests and linting
├── prompt.md         # Instructions for the AI model
├── context.txt       # Generated: code sent to AI
└── ai_output.txt     # Generated: AI response
```

## Next Steps

1. **Test the pipeline**: Run it once manually to verify everything works
2. **Tune the prompt**: Adjust `.ci/prompt.md` for your specific needs
3. **Set limits**: Consider limiting files processed to avoid timeout
4. **Add approval gate**: Uncomment the approval stage if you want manual review before PR creation

## Advanced Options

### Limit to specific files
In Jenkinsfile.ai, change:
```groovy
TARGET_PATHS = 'backend/routes backend/utils frontend/src/components'
```

### Use file replacement instead of patches
In Jenkinsfile.ai, change:
```groovy
OUTPUT_MODE = 'file'  // AI returns complete file contents
```

### Reduce context size
In `ai_apply.sh`, modify the find command to include only certain file types or limit depth.

### Add manual approval
Add this stage before "Create Pull Request":
```groovy
stage('Approval Gate') {
  steps {
    timeout(time: 10, unit: 'MINUTES') {
      input message: 'Review changes. Create PR?', ok: 'Proceed'
    }
  }
}
```
