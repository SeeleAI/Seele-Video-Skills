# Shared image call contract

Do not implement an image provider in this skill.

## Policy

- Default and only allowed model for this workflow: `gpt-image-2`.
- Set no-fallback behavior. A provider route change serving the same model may be reported, but an alternate model is not allowed.
- Show the final three prompts and expected paid call count, then obtain explicit approval immediately before generation.
- If approval is absent, stop at a complete dry-run package.
- If the executor reports a different model, billing/auth failure, or no usable URL/file, stop and preserve the receipt without secrets.

## Executor routing

- In an OpenClaw environment, use the existing shared media executor at `your configured image-generation adapter`; invoke its image command with `--model gpt-image-2 --no-fallback`.
- In the deployed Seele runtime, call the existing `ai-model-calling` skill's image executor with `model_choice: gpt-image-2` and its documented paid-model confirmation. Do not copy its scripts or credentials.

Record per call: prompt file, requested model, no-fallback flag, requested size/orientation, selected output, retry reason, and public/local asset reference. Never record tokens or secrets.
