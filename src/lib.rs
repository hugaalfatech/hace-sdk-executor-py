//! HACE SDK — Python Executor (NEP-PY)
//!
//! Bridges Runinfer ME Core to Python NEP via llama-cpp-python (hace-llm-machine).
//!
//! CANON: CSA-RUNINFER-BACKEND-CONFLICT.ail §3.2-3.4
//! CANON: hace-llm-machine manifest.ail (MactorResourceGovernor, KVCacheManager, SIOAdapter)
//!
//! This crate implements MactorBackend trait using llama-cpp-python via PyO3.
//!
//! ```text
//! Runinfer (ME Core)          Python NEP (nep-py)
//!     │                            │
//!     ▼                            ▼
//! MactorBackend trait        MactorResourceGovernor
//!     │                            │
//!     ├── load()            ──►    llama_cpp.Llama()
//!     ├── infer()           ──►    llama(prompt, ...)
//!     ├── health_check()    ──►    llama.health_check()
//!     ├── unload()          ──►    llama.unload()
//!     └── fingerprint()     ──►    model_hash + metadata
//! ```
//!
//! Transport: FDI (rac:cri.fdi → ffi) — direct call, zero-payload, deterministic

use std::fmt;
use std::sync::{Arc, Mutex};
use serde::{Deserialize, Serialize};
use thiserror::Error;

use hace_sdk_me_core::hooks::{Hook, HookContext, HookResult, HookError, HookMode, HookPriority};
use hace_sdk_runinfer::{
    MactorBackend, MactorConfig, InferenceRequest, InferenceResult, 
    ModelFingerprint, MactorError, HealthMonitor, MactorState, MactorLifecycle,
};

/// Python Executor — wraps llama-cpp-python (hace-llm-machine)
/// Implements MactorBackend trait for Runinfer ME Core
pub struct PythonExecutor {
    /// Python interpreter handle
    python: Option<pyo3::Python<'static>>,
    /// Llama model instance (via PyO3)
    llama: Option<pyo3::Py<pyo3::PyAny>>,
    /// Model fingerprint (FEH)
    fingerprint: Option<ModelFingerprint>,
    /// Health monitor
    health: HealthMonitor,
    /// Model configuration
    config: MactorConfig,
    /// Lifecycle state
    lifecycle: MactorLifecycle,
    /// Loaded model path
    model_path: String,
}

impl PythonExecutor {
    /// Create new PythonExecutor with config
    pub fn new(config: MactorConfig) -> Self {
        Self {
            python: None,
            llama: None,
            fingerprint: None,
            health: HealthMonitor::default(),
            config,
            lifecycle: MactorLifecycle::new(),
            model_path: String::new(),
        }
    }

    /// Initialize Python interpreter
    fn init_python(&mut self) -> Result<(), PythonExecutorError> {
        if self.python.is_none() {
            pyo3::prepare_freethreaded_python();
            let gil = pyo3::Python::acquire_gil();
            self.python = Some(unsafe { std::mem::transmute(gil.python()) });
        }
        Ok(())
    }

    /// Load llama-cpp-python module
    fn import_llama_cpp(&self) -> Result<pyo3::Py<pyo3::PyModule>, PythonExecutorError> {
        let py = self.python.as_ref().ok_or(PythonExecutorError::PythonNotInitialized)?;
        py.allow_threads(|| {
            py.import("llama_cpp").map_err(|e| {
                PythonExecutorError::ImportError(format!("Failed to import llama_cpp: {}", e))
            })
        }).map(|m| m.into())
    }

    /// Get Python GIL and return Python instance
    fn python(&self) -> Result<pyo3::Python<'_>, PythonExecutorError> {
        Ok(self.python.as_ref()
            .ok_or(PythonExecutorError::PythonNotInitialized)?
            .clone())
    }
}

impl MactorBackend for PythonExecutor {
    fn load(&mut self) -> Result<(), MactorError> {
        // Initialize Python
        self.init_python()?;
        
        // Transition lifecycle
        self.lifecycle.transition(MactorState::Loading)
            .map_err(MactorError::Lifecycle)?;

        let py = self.python()?;
        
        // Import llama_cpp
        let llama_cpp = self.import_llama_cpp()?;
        
        // Build Llama constructor arguments
        let kwargs = pyo3::types::PyDict::new(py);
        kwargs.set_item("model_path", &self.config.model_uri)?;
        kwargs.set_item("n_ctx", self.config.context_size)?;
        kwargs.set_item("n_threads", 4)?;
        kwargs.set_item("verbose", false)?;
        kwargs.set_item("use_mmap", true)?;
        kwargs.set_item("use_mlock", false)?;

        // Create Llama instance
        let llama_class = llama_cpp.getattr("Llama")
            .map_err(|e| PythonExecutorError::AttributeError(e.to_string()))?;
        
        let llama_instance = llama_class.call((), Some(&kwargs))
            .map_err(|e| PythonExecutorError::CallError(e.to_string()))?;

        // Store as Py<PyAny>
        self.llama = Some(llama_instance.into_py(py));
        self.model_path = self.config.model_uri.clone();

        // Compute fingerprint (model hash)
        let hash = compute_model_hash(&self.model_path);
        self.fingerprint = Some(ModelFingerprint {
            model_id: "llama".to_string(),
            model_hash: hash,
            format: "gguf".to_string(),
            context_limit: self.config.context_size,
        });

        // Transition to Ready
        self.lifecycle.transition(MactorState::Ready)
            .map_err(MactorError::Lifecycle)?;

        self.health.record_success();
        Ok(())
    }

    fn infer(&mut self, request: InferenceRequest) -> Result<InferenceResult, MactorError> {
        // Ensure loaded
        if !self.lifecycle.is_ready() {
            self.load()?;
        }

        let py = self.python()?;
        let llama = self.llama.as_ref()
            .ok_or(MactorError::LoadError("Model not loaded".into()))?;

        // Transition to Busy
        self.lifecycle.transition(MactorState::Busy)
            .map_err(MactorError::Lifecycle)?;

        // Prepare inference parameters
        let kwargs = pyo3::types::PyDict::new(py);
        kwargs.set_item("prompt", &request.prompt)?;
        kwargs.set_item("max_tokens", request.max_tokens)?;
        kwargs.set_item("temperature", request.temperature)?;
        
        // Add grammar if output_schema provided
        if let Some(schema) = &request.output_schema {
            kwargs.set_item("grammar", schema)?;
        }
        kwargs.set_item("stop", pyo3::types::PyList::new(py, &["<|end|>"]))?;

        // Call inference
        let start = std::time::Instant::now();
        let result = llama.call_method(py, "generate", (request.prompt.clone(),), Some(&kwargs))
            .map_err(|e| PythonExecutorError::CallError(e.to_string()))?;
        
        let latency_ms = start.elapsed().as_millis() as u64;

        // Parse result
        let text: String = result.extract(py)
            .map_err(|e| PythonExecutorError::ExtractError(e.to_string()))?;

        // Transition back to Ready
        self.lifecycle.transition(MactorState::Ready)
            .map_err(MactorError::Lifecycle)?;

        self.health.record_success();

        Ok(InferenceResult {
            text,
            structured_output: serde_json::json!({}),
            usage: serde_json::json!({"total_tokens": 0}),
            model_fingerprint: self.fingerprint.clone(),
            latency_ms,
        })
    }

    fn health_check(&self) -> bool {
        self.lifecycle.is_ready() && self.health.is_healthy() && self.llama.is_some()
    }

    fn unload(&mut self) -> Result<(), MactorError> {
        // Release llama instance
        self.llama = None;
        self.fingerprint = None;
        self.model_path.clear();
        
        // Transition to Unloaded
        self.lifecycle.transition(MactorState::Unloaded)
            .map_err(MactorError::Lifecycle)?;

        Ok(())
    }

    fn fingerprint(&self) -> Option<ModelFingerprint> {
        self.fingerprint.clone()
    }
}

/// Compute simple model hash from path (for FEH fingerprint)
fn compute_model_hash(path: &str) -> String {
    use std::collections::hash_map::DefaultHasher;
    use std::hash::{Hash, Hasher};
    let mut hasher = DefaultHasher::new();
    path.hash(&mut hasher);
    format!("{:x}", hasher.finish())
}

/// Python Executor errors
#[derive(Debug, Error)]
pub enum PythonExecutorError {
    #[error("Python not initialized")]
    PythonNotInitialized,
    #[error("Import error: {0}")]
    ImportError(String),
    #[error("Attribute error: {0}")]
    AttributeError(String),
    #[error("Call error: {0}")]
    CallError(String),
    #[error("Extract error: {0}")]
    ExtractError(String),
}

impl From<PythonExecutorError> for MactorError {
    fn from(e: PythonExecutorError) -> Self {
        MactorError::LoadError(e.to_string())
    }
}

/// PythonExecutor hook for FEM lifecycle integration
/// Per hace-llm-machine manifest.ail (FEM lifecycle hooks)
pub struct PythonExecutorHook {
    pub id: String,
    pub mode: HookMode,
    pub priority: HookPriority,
    pub executor: Arc<Mutex<PythonExecutor>>,
}

impl Hook for PythonExecutorHook {
    fn id(&self) -> &str { &self.id }
    fn mode(&self) -> HookMode { self.mode }
    fn priority(&self) -> HookPriority { self.priority }

    fn execute(&self, context: &HookContext) -> Result<HookResult, HookError> {
        let mut executor = self.executor.lock().map_err(|e| HookError {
            hook_id: self.id.clone(),
            message: e.to_string(),
        })?;

        match context.hook_id.as_str() {
            "fem.lifecycle.init" => {
                executor.load().map_err(|e| HookError {
                    hook_id: self.id.clone(),
                    message: e.to_string(),
                })?;
                Ok(HookResult::Continue)
            }
            "fem.lifecycle.health" => {
                if executor.health_check() {
                    Ok(HookResult::Continue)
                } else {
                    Ok(HookResult::Failed("Health check failed".into()))
                }
            }
            "fem.lifecycle.stop" => {
                executor.unload().map_err(|e| HookError {
                    hook_id: self.id.clone(),
                    message: e.to_string(),
                })?;
                Ok(HookResult::Continue)
            }
            _ => Ok(HookResult::Continue),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn python_executor_config() {
        let config = MactorConfig::default();
        let executor = PythonExecutor::new(config);
        assert!(!executor.lifecycle.is_ready());
        assert!(executor.llama.is_none());
    }

    #[test]
    fn python_executor_lifecycle_transitions() {
        let mut executor = PythonExecutor::new(MactorConfig::default());
        assert_eq!(executor.lifecycle.state, MactorState::Uninitialized);
    }

    #[test]
    fn python_executor_hook_id() {
        let config = MactorConfig::default();
        let executor = Arc::new(Mutex::new(PythonExecutor::new(config)));
        let hook = PythonExecutorHook {
            id: "test.python.executor".into(),
            mode: HookMode::Soft,
            priority: HookPriority(10),
            executor,
        };
        assert_eq!(hook.id(), "test.python.executor");
    }
}