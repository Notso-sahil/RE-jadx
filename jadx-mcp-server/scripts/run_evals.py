import asyncio
import os
import time
import json
import logging
from langsmith import Client
from langsmith.evaluation import evaluate, EvaluationResult, run_evaluator

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("jadx-evals")

# Try to load .env file manually so it works out of the box
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))
if os.path.exists(env_path):
    with open(env_path, 'r') as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                k, v = line.strip().split('=', 1)
                os.environ[k] = v.strip('"\'')

# Ensure API key is set for evaluations
if not os.environ.get("LANGSMITH_API_KEY"):
    logger.warning("LANGSMITH_API_KEY is not set. Evaluations will fail if LangSmith cannot authenticate.")

# Note: We must import the tools AFTER setting environment variables if we want them to pick up tracing,
# but for the EVALUATOR itself, we are running the functions and evaluating their outputs.
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.server.tools.outline_tools import get_class_outline, _token_estimate
from src.server.tools.class_tools import get_class_source

# -----------------------------------------------------------------------------
# 1. Mock Data / Dataset Definition
# -----------------------------------------------------------------------------
# For resume stats, we want to prove "Token Reduction" and "Latency Savings".
# We will create a synthetic evaluation dataset if we don't have a real APK loaded,
# but ideally, this runs against a loaded APK.

DATASET_NAME = "JADX Token Optimization Benchmark v2"

# We will define a few class names to test. If JADX is running and has an APK loaded,
# these should be actual classes in the APK. If not, the eval will still run but might
# get error responses from JADX.
EVAL_INPUTS = [
    {"class_name": "com.zesolaropo.xubavodujaguputuha.R"},
    {"class_name": "kotlin.coroutines.jvm.internal.BaseContinuationImpl"}, 
    {"class_name": "b7.g0cw.hx4tj7.a"}, # Guessing an obfuscated class name 'a'
]

# -----------------------------------------------------------------------------
# 2. Custom Evaluators
# -----------------------------------------------------------------------------

@run_evaluator
def token_reduction_evaluator(run, example) -> EvaluationResult:
    """
    Evaluates if the get_class_outline tool successfully reduced tokens by > 70%
    compared to the full class source.
    """
    # The output of our target function (get_class_outline)
    output = run.outputs
    
    if not output or "error" in output:
        return EvaluationResult(key="token_reduction_pct", score=0.0, comment="Tool returned an error or empty output.")

    # We expect our tool to return these metrics natively
    reduction_pct = output.get("reduction_pct", 0.0)
    
    # Score is 1.0 if reduction > 70%, else a partial score.
    score = 1.0 if reduction_pct >= 70.0 else (reduction_pct / 100.0)
    
    return EvaluationResult(
        key="token_reduction_pct",
        score=score,
        comment=f"Reduced tokens by {reduction_pct}%"
    )

@run_evaluator
def latency_evaluator(run, example) -> EvaluationResult:
    """
    Evaluates if the tool executed within an acceptable timeframe (< 500ms for outline).
    """
    # run.end_time and run.start_time are datetime objects
    if run.end_time and run.start_time:
        latency_ms = (run.end_time - run.start_time).total_seconds() * 1000
    else:
        latency_ms = 9999
        
    score = 1.0 if latency_ms < 500 else max(0.0, 1.0 - (latency_ms - 500) / 1000.0)
    
    return EvaluationResult(
        key="latency_ms",
        score=score,
        comment=f"Latency: {latency_ms:.1f}ms"
    )

# -----------------------------------------------------------------------------
# 3. Target Function (The pipeline we are evaluating)
# -----------------------------------------------------------------------------

async def evaluate_outline_tool(inputs: dict) -> dict:
    """
    The target function we are evaluating. 
    It calls the JADX MCP get_class_outline tool.
    """
    class_name = inputs["class_name"]
    # Call the actual MCP tool function
    result = await get_class_outline(class_name)
    return result

# Wrapper to run async target synchronously for LangSmith evaluate()
def target_wrapper(inputs: dict) -> dict:
    return asyncio.run(evaluate_outline_tool(inputs))

# -----------------------------------------------------------------------------
# 4. Main Evaluation Runner
# -----------------------------------------------------------------------------

def main():
    client = Client()
    
    # 1. Setup Dataset
    logger.info(f"Setting up dataset: {DATASET_NAME}")
    if not client.has_dataset(dataset_name=DATASET_NAME):
        dataset = client.create_dataset(
            dataset_name=DATASET_NAME,
            description="Benchmark for evaluating JADX MCP token optimization strategies."
        )
        for idx, inp in enumerate(EVAL_INPUTS):
            client.create_example(
                inputs=inp,
                outputs={"expected_success": True},
                dataset_id=dataset.id,
            )
    
    # 2. Run Evaluation
    logger.info("Running evaluation suite...")
    experiment_prefix = "JADX-Outline-Eval"
    
    results = evaluate(
        target_wrapper,
        data=DATASET_NAME,
        evaluators=[token_reduction_evaluator, latency_evaluator],
        experiment_prefix=experiment_prefix,
    )
    
    logger.info("Evaluation complete. View results in LangSmith UI.")

if __name__ == "__main__":
    main()
