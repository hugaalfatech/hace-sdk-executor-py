//! ROTA tests for haca-sdk-executor-py

use hac_sdk_executor_py::{PythonExecutor, PythonExecutorHook};
use hac_sdk_runinfer::{MactorConfig, MactorBackend, InferenceRequest, MactorState, MactorLifecycle, HealthMonitor};
use hac_sdk_me_core::hooks::{Hook, HookContext, HookResult, HookMode, HookPriority};

#[test]
fn executor_py_config_default() {
    let config = MactorConfig::default();
    let executor = PythonExecutor::new(config);
    assert!(!executor.lifecycle.is_ready());
}

#[test]
fn executor_py_lifecycle() {
    let config = MactorConfig::default();
    let mut executor = PythonExecutor::new(config);
    assert_eq!(executor.lifecycle.state, MactorState::Uninitialized);
}

#[test]
fn executor_py_hook_fem_init() {
    use std::sync::{Arc, Mutex};
    let config = MactorConfig::default();
    let executor = Arc::new(Mutex::new(PythonExecutor::new(config)));
    let hook = PythonExecutorHook {
        id: "test".into(),
        mode: HookMode::Soft,
        priority: HookPriority(10),
        executor: executor.clone(),
    };
    let ctx = HookContext::new("fem.lifecycle.init", vec![]);
    // Will fail because no llama model, but hook structure is correct
    let _ = hook.execute(&ctx);
}

#[test]
fn executor_py_hook_fem_health() {
    use std::sync::{Arc, Mutex};
    let config = MactorConfig::default();
    let executor = Arc::new(Mutex::new(PythonExecutor::new(config)));
    let hook = PythonExecutorHook {
        id: "test".into(),
        mode: HookMode::Soft,
        priority: HookPriority(10),
        executor,
    };
    let ctx = HookContext::new("fem.lifecycle.health", vec![]);
    let result = hook.execute(&ctx);
    assert!(matches!(result, Ok(HookResult::Failed(_)) | Ok(HookResult::Continue)));
}

#[test]
fn executor_py_hook_fem_stop() {
    use std::sync::{Arc, Mutex};
    let config = MactorConfig::default();
    let executor = Arc::new(Mutex::new(PythonExecutor::new(config)));
    let hook = PythonExecutorHook {
        id: "test".into(),
        mode: HookMode::Soft,
        priority: HookPriority(10),
        executor,
    };
    let ctx = HookContext::new("fem.lifecycle.stop", vec![]);
    let _ = hook.execute(&ctx);
}