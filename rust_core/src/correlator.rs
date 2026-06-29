//! Event Correlation Engine
//!
//! High-performance event correlation for UI ↔ API ↔ Navigation
//! 
//! This module provides fast correlation of:
//! - UI interactions with API calls
//! - Navigation transitions with API responses
//! - User actions with backend events

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use std::collections::HashMap;
use serde::{Serialize, Deserialize};

/// Event types that can be correlated
#[derive(Debug, Clone, Serialize, Deserialize)]
#[pyclass]
pub enum EventType {
    #[pyo3(name = "UI_INTERACTION")]
    UiInteraction,
    #[pyo3(name = "API_CALL")]
    ApiCall,
    #[pyo3(name = "API_RESPONSE")]
    ApiResponse,
    #[pyo3(name = "NAVIGATION")]
    Navigation,
    #[pyo3(name = "SCREEN_CHANGE")]
    ScreenChange,
}

/// A single event in the timeline
#[derive(Debug, Clone)]
#[pyclass]
pub struct Event {
    #[pyo3(get, set)]
    pub event_id: String,
    #[pyo3(get, set)]
    pub event_type: String,
    #[pyo3(get, set)]
    pub timestamp: f64,
    #[pyo3(get, set)]
    pub data: HashMap<String, String>,
}

#[pymethods]
impl Event {
    #[new]
    fn new(event_id: String, event_type: String, timestamp: f64) -> Self {
        Self {
            event_id,
            event_type,
            timestamp,
            data: HashMap::new(),
        }
    }

    fn add_data(&mut self, key: String, value: String) {
        self.data.insert(key, value);
    }

    fn __repr__(&self) -> String {
        format!(
            "Event(id={}, type={}, time={:.3})",
            self.event_id, self.event_type, self.timestamp
        )
    }
}

/// Correlation result between two events
#[derive(Debug, Clone)]
#[pyclass]
pub struct Correlation {
    #[pyo3(get)]
    pub source_event_id: String,
    #[pyo3(get)]
    pub target_event_id: String,
    #[pyo3(get)]
    pub confidence: f64,
    #[pyo3(get)]
    pub time_delta_ms: f64,
    #[pyo3(get)]
    pub correlation_type: String,
}

#[pymethods]
impl Correlation {
    fn __repr__(&self) -> String {
        format!(
            "Correlation({}→{}, confidence={:.2}, delta={:.0}ms, type={})",
            self.source_event_id,
            self.target_event_id,
            self.confidence,
            self.time_delta_ms,
            self.correlation_type
        )
    }
}

/// High-performance event correlator
#[pyclass]
pub struct RustCorrelator {
    events: Vec<Event>,
    max_time_delta_ms: f64,
    min_confidence: f64,
}

#[pymethods]
impl RustCorrelator {
    #[new]
    #[pyo3(signature = (max_time_delta_ms=5000.0, min_confidence=0.5))]
    fn new(max_time_delta_ms: f64, min_confidence: f64) -> Self {
        Self {
            events: Vec::new(),
            max_time_delta_ms,
            min_confidence,
        }
    }

    /// Add an event to the timeline
    fn add_event(&mut self, event: Event) {
        self.events.push(event);
    }

    /// Add multiple events from Python
    fn add_events(&mut self, py: Python, events: &PyList) -> PyResult<()> {
        for item in events.iter() {
            let event: Event = item.extract()?;
            self.events.push(event);
        }
        Ok(())
    }

    /// Clear all events
    fn clear(&mut self) {
        self.events.clear();
    }

    /// Get number of events
    fn len(&self) -> usize {
        self.events.len()
    }

    /// Find correlations between events
    fn find_correlations(&self, py: Python) -> PyResult<PyObject> {
        let correlations = self.correlate_events();
        
        // Convert to Python list
        let py_list = PyList::empty(py);
        for corr in correlations {
            py_list.append(Py::new(py, corr)?)?;
        }
        
        Ok(py_list.into())
    }

    /// Correlate UI interactions with API calls
    fn correlate_ui_to_api(&self, py: Python) -> PyResult<PyObject> {
        let mut correlations = Vec::new();

        // Find UI → API correlations
        for ui_event in &self.events {
            if ui_event.event_type != "UI_INTERACTION" {
                continue;
            }

            // Look for API calls within time window
            for api_event in &self.events {
                if api_event.event_type != "API_CALL" {
                    continue;
                }

                let time_delta = api_event.timestamp - ui_event.timestamp;
                
                // Skip if outside time window or in wrong order
                if time_delta < 0.0 || time_delta > self.max_time_delta_ms {
                    continue;
                }

                // Calculate confidence based on timing and context
                let confidence = self.calculate_confidence(ui_event, api_event, time_delta);

                if confidence >= self.min_confidence {
                    correlations.push(Correlation {
                        source_event_id: ui_event.event_id.clone(),
                        target_event_id: api_event.event_id.clone(),
                        confidence,
                        time_delta_ms: time_delta,
                        correlation_type: "UI_TO_API".to_string(),
                    });
                }
            }
        }

        // Convert to Python list
        let py_list = PyList::empty(py);
        for corr in correlations {
            py_list.append(Py::new(py, corr)?)?;
        }
        
        Ok(py_list.into())
    }

    /// Correlate API responses with navigation changes
    fn correlate_api_to_navigation(&self, py: Python) -> PyResult<PyObject> {
        let mut correlations = Vec::new();

        for api_event in &self.events {
            if api_event.event_type != "API_RESPONSE" {
                continue;
            }

            // Look for navigation changes after API response
            for nav_event in &self.events {
                if nav_event.event_type != "NAVIGATION" && nav_event.event_type != "SCREEN_CHANGE" {
                    continue;
                }

                let time_delta = nav_event.timestamp - api_event.timestamp;
                
                if time_delta < 0.0 || time_delta > self.max_time_delta_ms {
                    continue;
                }

                let confidence = self.calculate_confidence(api_event, nav_event, time_delta);

                if confidence >= self.min_confidence {
                    correlations.push(Correlation {
                        source_event_id: api_event.event_id.clone(),
                        target_event_id: nav_event.event_id.clone(),
                        confidence,
                        time_delta_ms: time_delta,
                        correlation_type: "API_TO_NAVIGATION".to_string(),
                    });
                }
            }
        }

        let py_list = PyList::empty(py);
        for corr in correlations {
            py_list.append(Py::new(py, corr)?)?;
        }
        
        Ok(py_list.into())
    }

    /// Build correlation graph as adjacency list
    fn build_correlation_graph(&self, py: Python) -> PyResult<PyObject> {
        let correlations = self.correlate_events();
        
        // Build adjacency list
        let mut graph: HashMap<String, Vec<String>> = HashMap::new();
        
        for corr in correlations {
            graph
                .entry(corr.source_event_id.clone())
                .or_insert_with(Vec::new)
                .push(corr.target_event_id.clone());
        }

        // Convert to Python dict
        let py_dict = PyDict::new(py);
        for (source, targets) in graph {
            let py_list = PyList::empty(py);
            for target in targets {
                py_list.append(target)?;
            }
            py_dict.set_item(source, py_list)?;
        }

        Ok(py_dict.into())
    }

    /// Get correlation statistics
    fn get_statistics(&self, py: Python) -> PyResult<PyObject> {
        let correlations = self.correlate_events();
        
        let total = correlations.len();
        let avg_confidence = if total > 0 {
            correlations.iter().map(|c| c.confidence).sum::<f64>() / total as f64
        } else {
            0.0
        };
        
        let avg_time_delta = if total > 0 {
            correlations.iter().map(|c| c.time_delta_ms).sum::<f64>() / total as f64
        } else {
            0.0
        };

        // Count by type
        let mut by_type: HashMap<String, usize> = HashMap::new();
        for corr in &correlations {
            *by_type.entry(corr.correlation_type.clone()).or_insert(0) += 1;
        }

        // Build result dict
        let stats = PyDict::new(py);
        stats.set_item("total_correlations", total)?;
        stats.set_item("avg_confidence", avg_confidence)?;
        stats.set_item("avg_time_delta_ms", avg_time_delta)?;
        
        let by_type_dict = PyDict::new(py);
        for (corr_type, count) in by_type {
            by_type_dict.set_item(corr_type, count)?;
        }
        stats.set_item("by_type", by_type_dict)?;

        Ok(stats.into())
    }
}

// Implementation methods (not exposed to Python)
impl RustCorrelator {
    /// Internal: correlate all events
    fn correlate_events(&self) -> Vec<Correlation> {
        let mut correlations = Vec::new();

        // Sort events by timestamp for efficient correlation
        let mut sorted_events = self.events.clone();
        sorted_events.sort_by(|a, b| {
            // Handle NaN timestamps gracefully - treat NaN as greater than any value
            a.timestamp.partial_cmp(&b.timestamp).unwrap_or(std::cmp::Ordering::Greater)
        });

        // Correlate each event with subsequent events
        for (i, source) in sorted_events.iter().enumerate() {
            for target in sorted_events.iter().skip(i + 1) {
                let time_delta = target.timestamp - source.timestamp;

                // Stop if we're outside the time window
                if time_delta > self.max_time_delta_ms {
                    break;
                }

                // Check if these event types should be correlated
                if !self.should_correlate(&source.event_type, &target.event_type) {
                    continue;
                }

                let confidence = self.calculate_confidence(source, target, time_delta);

                if confidence >= self.min_confidence {
                    let correlation_type = format!("{}_{}", 
                        self.normalize_event_type(&source.event_type),
                        self.normalize_event_type(&target.event_type)
                    );

                    correlations.push(Correlation {
                        source_event_id: source.event_id.clone(),
                        target_event_id: target.event_id.clone(),
                        confidence,
                        time_delta_ms: time_delta,
                        correlation_type,
                    });
                }
            }
        }

        correlations
    }

    /// Calculate correlation confidence score
    fn calculate_confidence(&self, source: &Event, target: &Event, time_delta: f64) -> f64 {
        let mut confidence = 0.0;

        // Time proximity (closer in time = higher confidence)
        let time_score = 1.0 - (time_delta / self.max_time_delta_ms);
        confidence += time_score * 0.4;

        // Event type compatibility
        if self.are_compatible_types(&source.event_type, &target.event_type) {
            confidence += 0.3;
        }

        // Data correlation (check if events share common data)
        let data_score = self.calculate_data_similarity(source, target);
        confidence += data_score * 0.3;

        confidence.min(1.0)
    }

    /// Check if two event types should be correlated
    fn should_correlate(&self, source_type: &str, target_type: &str) -> bool {
        matches!(
            (source_type, target_type),
            ("UI_INTERACTION", "API_CALL") |
            ("API_CALL", "API_RESPONSE") |
            ("API_RESPONSE", "NAVIGATION") |
            ("API_RESPONSE", "SCREEN_CHANGE") |
            ("UI_INTERACTION", "NAVIGATION")
        )
    }

    /// Check if event types are compatible for correlation
    fn are_compatible_types(&self, source_type: &str, target_type: &str) -> bool {
        self.should_correlate(source_type, target_type)
    }

    /// Calculate data similarity between events
    fn calculate_data_similarity(&self, source: &Event, target: &Event) -> f64 {
        if source.data.is_empty() || target.data.is_empty() {
            return 0.0;
        }

        let common_keys: Vec<&String> = source.data.keys()
            .filter(|k| target.data.contains_key(*k))
            .collect();

        if common_keys.is_empty() {
            return 0.0;
        }

        // Count matching values.
        // common_keys is Vec<&String>, so .iter() yields &&String and the
        // closure binds k as &&&String; deref to &String (**k) for the HashMap
        // lookup, otherwise the key type is &String and String: Borrow<&String>
        // does not hold (E0277).
        let matches = common_keys.iter()
            .filter(|k| source.data.get(**k) == target.data.get(**k))
            .count();

        matches as f64 / common_keys.len() as f64
    }

    /// Normalize event type for correlation naming
    fn normalize_event_type(&self, event_type: &str) -> String {
        event_type.to_uppercase().replace(' ', "_")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_event_creation() {
        let event = Event::new(
            "evt_1".to_string(),
            "UI_INTERACTION".to_string(),
            1000.0,
        );
        assert_eq!(event.event_id, "evt_1");
        assert_eq!(event.event_type, "UI_INTERACTION");
        assert_eq!(event.timestamp, 1000.0);
    }

    #[test]
    fn test_correlator_basic() {
        let mut correlator = RustCorrelator::new(5000.0, 0.5);
        
        let ui_event = Event::new("ui_1".to_string(), "UI_INTERACTION".to_string(), 1000.0);
        let api_event = Event::new("api_1".to_string(), "API_CALL".to_string(), 1050.0);
        
        correlator.add_event(ui_event);
        correlator.add_event(api_event);
        
        assert_eq!(correlator.len(), 2);
    }

    #[test]
    fn test_correlation_calculation() {
        let correlator = RustCorrelator::new(5000.0, 0.5);
        
        let source = Event::new("src".to_string(), "UI_INTERACTION".to_string(), 1000.0);
        let target = Event::new("tgt".to_string(), "API_CALL".to_string(), 1100.0);
        
        let confidence = correlator.calculate_confidence(&source, &target, 100.0);
        assert!(confidence > 0.0);
        assert!(confidence <= 1.0);
    }

    #[test]
    fn test_should_correlate() {
        let correlator = RustCorrelator::new(5000.0, 0.5);
        
        assert!(correlator.should_correlate("UI_INTERACTION", "API_CALL"));
        assert!(correlator.should_correlate("API_RESPONSE", "NAVIGATION"));
        assert!(!correlator.should_correlate("UI_INTERACTION", "UI_INTERACTION"));
    }

    #[test]
    fn test_nan_timestamp_handling() {
        // Bug fix test: NaN timestamps should not cause panic
        let mut correlator = RustCorrelator::new(5000.0, 0.5);
        
        // Add events with valid timestamps
        let event1 = Event::new("e1".to_string(), "UI_INTERACTION".to_string(), 1000.0);
        let event2 = Event::new("e2".to_string(), "API_CALL".to_string(), 1100.0);
        
        // Add event with NaN timestamp
        let event_nan = Event::new("e_nan".to_string(), "UI_INTERACTION".to_string(), f64::NAN);
        
        correlator.add_event(event1);
        correlator.add_event(event2);
        correlator.add_event(event_nan);
        
        // These operations should not panic even with NaN timestamp
        let correlations = correlator.find_correlations();
        assert!(correlations.is_ok(), "find_correlations should not panic with NaN timestamps");
        
        let graph = correlator.build_correlation_graph();
        assert!(graph.is_ok(), "build_correlation_graph should not panic with NaN timestamps");
        
        let stats = correlator.get_statistics();
        assert!(stats.is_ok(), "get_statistics should not panic with NaN timestamps");
        
        // Valid events should still correlate properly
        let correlations = correlations.unwrap();
        let valid_correlations: Vec<_> = correlations
            .iter()
            .filter(|c| c.source_id != "e_nan" && c.target_id != "e_nan")
            .collect();
        
        // Should have at least one valid correlation between e1 and e2
        assert!(valid_correlations.len() > 0, "Valid events should still correlate");
    }

    #[test]
    fn test_infinity_timestamp_handling() {
        // Additional edge case: infinity timestamps
        let mut correlator = RustCorrelator::new(5000.0, 0.5);
        
        let event1 = Event::new("e1".to_string(), "UI_INTERACTION".to_string(), 1000.0);
        let event_inf = Event::new("e_inf".to_string(), "API_CALL".to_string(), f64::INFINITY);
        let event_neg_inf = Event::new("e_neg_inf".to_string(), "UI_INTERACTION".to_string(), f64::NEG_INFINITY);
        
        correlator.add_event(event1);
        correlator.add_event(event_inf);
        correlator.add_event(event_neg_inf);
        
        // Should not panic
        let result = correlator.find_correlations();
        assert!(result.is_ok(), "Should handle infinity timestamps without panic");
    }
}
