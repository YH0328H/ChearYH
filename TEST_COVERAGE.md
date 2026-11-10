# 测试覆盖统计

**最后更新**：2026-11-10

## 总体情况

- **总测试数**：29
- **通过**：28
- **跳过**：1
- **失败**：0
- **通过率**：96.6%

## 详细测试套件

### 主动表达（7 tests）
```
tests/test_proactive_integration.py::test_proactive_scheduler_initializes PASSED
tests/test_proactive_integration.py::test_check_proactive_returns_candidates PASSED
tests/test_proactive_integration.py::test_send_proactive_persists_expression PASSED
tests/test_proactive_integration.py::test_idle_trigger_activates PASSED
tests/test_proactive_integration.py::test_stress_trigger_activates PASSED
tests/test_proactive_integration.py::test_valence_gate_blocks_negative PASSED
tests/test_proactive_integration.py::test_arousal_gate_blocks_low_energy PASSED
```

### TTS 服务（8 tests, 1 skipped）
```
tests/test_tts.py::test_tts_service_initialization PASSED
tests/test_tts.py::test_generate_speech_async SKIPPED (edge-tts not installed)
tests/test_tts.py::test_generate_speech_sync PASSED
tests/test_tts.py::test_speech_caching PASSED
tests/test_tts.py::test_voice_selection PASSED
tests/test_tts.py::test_rate_adjustment PASSED
tests/test_tts.py::test_volume_adjustment PASSED
tests/test_tts.py::test_pitch_adjustment PASSED
tests/test_tts.py::test_invalid_text_handling PASSED
```

### 快速接话集成（6 tests）
```
tests/test_backchannel_integration.py::test_backchannel_scheduler_initializes PASSED
tests/test_backchannel_integration.py::test_backchannel_triggers_on_pause PASSED
tests/test_backchannel_integration.py::test_backchannel_tts_integration PASSED
tests/test_backchannel_integration.py::test_backchannel_cancellation PASSED
tests/test_backchannel_integration.py::test_backchannel_context_aware PASSED
tests/test_backchannel_integration.py::test_backchannel_rate_limiting PASSED
```

### 本地降级（5 tests）
```
tests/test_fallback.py::test_local_rule_provider_always_succeeds PASSED
tests/test_fallback.py::test_fallback_to_local_when_main_fails PASSED
tests/test_fallback.py::test_fallback_to_ollama PASSED
tests/test_fallback.py::test_ollama_provider_config PASSED
tests/test_fallback.py::test_fallback_chain_exhaustion PASSED
```

### 首次引导（5 tests）
```
tests/test_onboarding_integration.py::test_bootstrap_returns_onboarding_modules PASSED
tests/test_onboarding_integration.py::test_bootstrap_onboarding_not_completed_initially PASSED
tests/test_onboarding_integration.py::test_complete_onboarding_marks_as_done PASSED
tests/test_onboarding_integration.py::test_complete_onboarding_saves_local_fallback_preference PASSED
tests/test_onboarding_integration.py::test_complete_onboarding_without_preferences PASSED
```

### 工作模式隔离（4 tests）
```
tests/test_work_mode_isolation.py::test_companion_mode_writes_memory PASSED
tests/test_work_mode_isolation.py::test_work_mode_skips_memory PASSED
tests/test_work_mode_isolation.py::test_mode_switch_affects_memory_persistence PASSED
tests/test_work_mode_isolation.py::test_work_mode_still_returns_response PASSED
```

## 覆盖的模块

- `src/cether/proactive.py` - 主动表达调度
- `src/cether/tts.py` - TTS 服务
- `src/cether/backchannel.py` - 快速接话
- `src/cether/providers.py` - FallbackProvider, OllamaProvider
- `src/cether/conversation.py` - 记忆隔离
- `src/cether/mode.py` - 模式控制
- `src/cether/desktop.py` - API 集成

## 待安装依赖

- `edge-tts>=7.0.0` - TTS 功能（可选，未安装时测试跳过）

