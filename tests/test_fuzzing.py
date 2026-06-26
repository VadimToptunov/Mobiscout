"""
Unit tests for STEP 8: Fuzzing Module

Comprehensive testing of fuzzing strategies, input generation, and campaign management.
Includes positive, negative, and edge case tests.
"""

import pytest

from framework.fuzzing import (
    FuzzingStrategy,
    InputType,
    FuzzInput,
    FuzzResult,
    FuzzGenerator,
    MutationFuzzer,
    UIFuzzer,
    APIFuzzer,
    FuzzingCampaign
)


class TestFuzzingStrategy:
    """Test FuzzingStrategy enum"""

    def test_all_strategies(self):
        """Test all fuzzing strategies"""
        strategies = [
            FuzzingStrategy.RANDOM,
            FuzzingStrategy.MUTATION,
            FuzzingStrategy.GRAMMAR,
            FuzzingStrategy.BOUNDARY,
            FuzzingStrategy.ML_ASSISTED
        ]
        assert len(strategies) == 5


class TestInputType:
    """Test InputType enum"""

    def test_all_input_types(self):
        """Test all input types"""
        types = [
            InputType.TEXT,
            InputType.NUMBER,
            InputType.EMAIL,
            InputType.URL,
            InputType.PHONE,
            InputType.DATE,
            InputType.PASSWORD,
            InputType.JSON
        ]
        assert len(types) == 8


class TestFuzzGenerator:
    """Test FuzzGenerator"""

    def test_create_generator(self):
        """Test creating generator"""
        gen = FuzzGenerator(seed=42)
        assert gen is not None
        assert gen.special_chars
        assert gen.boundaries

    def test_generate_text_inputs(self):
        """Test text input generation"""
        gen = FuzzGenerator(seed=42)
        inputs = gen.generate(InputType.TEXT, count=10)

        assert len(inputs) == 10
        assert all(isinstance(i, FuzzInput) for i in inputs)
        assert all(i.input_type == InputType.TEXT for i in inputs)

    def test_text_inputs_include_edge_cases(self):
        """Test text inputs include important edge cases"""
        gen = FuzzGenerator(seed=42)
        inputs = gen.generate(InputType.TEXT, count=20)

        patterns = [i.metadata.get('pattern') for i in inputs]

        # Should include SQL injection
        assert any('sql_injection' in str(p) for p in patterns)
        # Should include XSS
        assert any('xss' in str(p) for p in patterns)
        # Should include path traversal
        assert any('path_traversal' in str(p) for p in patterns)

    def test_generate_number_inputs(self):
        """Test number input generation"""
        gen = FuzzGenerator(seed=42)
        inputs = gen.generate(InputType.NUMBER, count=10)

        assert len(inputs) == 10
        assert all(i.input_type == InputType.NUMBER for i in inputs)

        # Should include boundary values
        values = [i.value for i in inputs]
        assert 0 in values
        assert -1 in values
        assert 1 in values

    def test_generate_email_inputs(self):
        """Test email input generation"""
        gen = FuzzGenerator(seed=42)
        inputs = gen.generate(InputType.EMAIL, count=10)

        assert len(inputs) == 10
        assert all(i.input_type == InputType.EMAIL for i in inputs)

        # Should include valid and invalid emails
        patterns = [i.metadata.get('pattern') for i in inputs]
        assert 'valid_email' in patterns
        assert 'empty' in patterns

    def test_generate_url_inputs(self):
        """Test URL input generation"""
        gen = FuzzGenerator(seed=42)
        inputs = gen.generate(InputType.URL, count=10)

        assert len(inputs) == 10
        assert all(i.input_type == InputType.URL for i in inputs)

    def test_generate_phone_inputs(self):
        """Test phone input generation"""
        gen = FuzzGenerator(seed=42)
        inputs = gen.generate(InputType.PHONE, count=10)

        assert len(inputs) == 10
        assert all(i.input_type == InputType.PHONE for i in inputs)

    def test_generate_password_inputs(self):
        """Test password input generation"""
        gen = FuzzGenerator(seed=42)
        inputs = gen.generate(InputType.PASSWORD, count=10)

        assert len(inputs) == 10
        assert all(i.input_type == InputType.PASSWORD for i in inputs)

    def test_generate_json_inputs(self):
        """Test JSON input generation"""
        gen = FuzzGenerator(seed=42)
        inputs = gen.generate(InputType.JSON, count=10)

        assert len(inputs) == 10
        assert all(i.input_type == InputType.JSON for i in inputs)


class TestMutationFuzzer:
    """Test MutationFuzzer"""

    def test_create_mutation_fuzzer(self):
        """Test creating mutation fuzzer"""
        fuzzer = MutationFuzzer(seed=42)
        assert fuzzer is not None

    def test_mutate_string(self):
        """Test string mutation"""
        fuzzer = MutationFuzzer(seed=42)
        original = "test_input"

        mutated = fuzzer.mutate(original, mutations=5)

        assert len(mutated) == 5
        assert all(isinstance(m, FuzzInput) for m in mutated)
        assert all(m.strategy == FuzzingStrategy.MUTATION for m in mutated)
        assert all(m.metadata['original'] == original for m in mutated)

    def test_mutate_empty_string(self):
        """Test mutation of empty string"""
        fuzzer = MutationFuzzer(seed=42)
        mutated = fuzzer.mutate("", mutations=3)

        assert len(mutated) == 3
        # Should produce some output even for empty input
        assert all(m.value for m in mutated)

    def test_mutation_types(self):
        """Test different mutation types are applied"""
        fuzzer = MutationFuzzer(seed=42)
        original = "test"

        mutated = fuzzer.mutate(original, mutations=20)

        # Should have variety of mutations
        values = [m.value for m in mutated]
        assert len(set(values)) > 1  # Not all same


class TestUIFuzzer:
    """Test UIFuzzer"""

    def test_create_ui_fuzzer(self):
        """Test creating UI fuzzer"""
        fuzzer = UIFuzzer()
        assert fuzzer is not None
        assert fuzzer.generator is not None
        assert fuzzer.mutator is not None

    def test_fuzz_text_field(self):
        """Test fuzzing text field"""
        fuzzer = UIFuzzer()
        results = fuzzer.fuzz_text_field("email_field", InputType.EMAIL, count=20)

        assert len(results) == 20
        assert all(isinstance(r, FuzzResult) for r in results)
        assert len(fuzzer.results) == 20

    def test_fuzz_button_clicks(self):
        """Test fuzzing button clicks"""
        fuzzer = UIFuzzer()
        results = fuzzer.fuzz_button_clicks("submit_button", count=50)

        assert len(results) == 50
        assert all(isinstance(r, FuzzResult) for r in results)

    def test_get_crash_inputs(self):
        """Test getting crash inputs"""
        fuzzer = UIFuzzer()
        fuzzer.fuzz_text_field("test_field", count=100)

        crashes = fuzzer.get_crash_inputs()

        # Should have some crashes (1% crash rate)
        assert isinstance(crashes, list)
        # With 100 inputs and 1% crash rate, likely to have at least one

    def test_get_statistics(self):
        """Test getting fuzzing statistics"""
        fuzzer = UIFuzzer()
        fuzzer.fuzz_text_field("test_field", count=50)

        stats = fuzzer.get_statistics()

        assert 'total_inputs' in stats
        assert 'crashes' in stats
        assert 'errors' in stats
        assert 'successes' in stats
        assert 'crash_rate' in stats
        assert 'avg_response_time_ms' in stats

        assert stats['total_inputs'] == 50

    def test_statistics_empty_results(self):
        """Test statistics with no results"""
        fuzzer = UIFuzzer()
        stats = fuzzer.get_statistics()

        assert stats == {}


class TestAPIFuzzer:
    """Test APIFuzzer"""

    def test_create_api_fuzzer(self):
        """Test creating API fuzzer"""
        fuzzer = APIFuzzer()
        assert fuzzer is not None
        assert fuzzer.generator is not None

    def test_fuzz_endpoint(self):
        """Test fuzzing API endpoint"""
        fuzzer = APIFuzzer()
        results = fuzzer.fuzz_endpoint("POST", "/api/login", InputType.EMAIL, count=30)

        assert len(results) == 30
        assert all(isinstance(r, FuzzResult) for r in results)
        assert len(fuzzer.results) == 30

    def test_get_vulnerable_endpoints(self):
        """Test getting vulnerable endpoints"""
        fuzzer = APIFuzzer()

        # Fuzz multiple endpoints
        fuzzer.fuzz_endpoint("POST", "/api/login", InputType.TEXT, count=50)
        fuzzer.fuzz_endpoint("GET", "/api/users", InputType.NUMBER, count=50)

        vulnerable = fuzzer.get_vulnerable_endpoints()

        assert isinstance(vulnerable, list)
        # Some endpoints should be flagged as vulnerable (>10% error rate)
        for vuln in vulnerable:
            assert 'endpoint' in vuln
            assert 'error_rate' in vuln
            assert vuln['error_rate'] > 0.1


class TestFuzzingCampaign:
    """Test FuzzingCampaign"""

    def test_create_campaign(self):
        """Test creating fuzzing campaign"""
        campaign = FuzzingCampaign()
        assert campaign is not None
        assert campaign.ui_fuzzer is not None
        assert campaign.api_fuzzer is not None

    def test_run_ui_campaign(self):
        """Test running UI campaign"""
        campaign = FuzzingCampaign()

        targets = [
            {'id': 'email_field', 'type': 'text_field', 'input_type': 'email'},
            {'id': 'password_field', 'type': 'text_field', 'input_type': 'password'},
            {'id': 'submit_button', 'type': 'button'}
        ]

        results = campaign.run_ui_campaign(targets)

        assert 'targets' in results
        assert 'total_inputs' in results
        assert 'crashes' in results
        assert 'start_time' in results
        assert 'end_time' in results
        assert 'statistics' in results

        assert len(results['targets']) == 3
        assert results['total_inputs'] > 0

    def test_run_api_campaign(self):
        """Test running API campaign"""
        campaign = FuzzingCampaign()

        endpoints = [
            {'method': 'POST', 'endpoint': '/api/login', 'param_type': 'email'},
            {'method': 'GET', 'endpoint': '/api/users', 'param_type': 'number'},
            {'method': 'PUT', 'endpoint': '/api/profile', 'param_type': 'json'}
        ]

        results = campaign.run_api_campaign(endpoints)

        assert 'endpoints' in results
        assert 'total_requests' in results
        assert 'errors' in results
        assert 'start_time' in results
        assert 'end_time' in results
        assert 'vulnerable_endpoints' in results

        assert len(results['endpoints']) == 3
        assert results['total_requests'] > 0

    def test_get_summary(self):
        """Test getting campaign summary"""
        campaign = FuzzingCampaign()

        # Run campaigns
        ui_targets = [{'id': 'field1', 'type': 'text_field'}]
        api_endpoints = [{'method': 'POST', 'endpoint': '/api/test'}]

        campaign.run_ui_campaign(ui_targets)
        campaign.run_api_campaign(api_endpoints)

        summary = campaign.get_summary()

        assert 'total_inputs' in summary
        assert 'total_crashes' in summary
        assert 'total_errors' in summary
        assert 'campaigns' in summary

        assert 'ui' in summary['campaigns']
        assert 'api' in summary['campaigns']
        assert summary['total_inputs'] > 0

    def test_export_report(self, tmp_path):
        """Test exporting campaign report"""
        campaign = FuzzingCampaign()

        targets = [{'id': 'test_field', 'type': 'text_field'}]
        campaign.run_ui_campaign(targets)

        output_path = tmp_path / "fuzzing_report.json"
        campaign.export_report(output_path)

        assert output_path.exists()

        # Verify JSON is valid
        import json
        with open(output_path) as f:
            data = json.load(f)

        assert 'ui' in data


class TestFuzzInputDataclass:
    """Test FuzzInput dataclass"""

    def test_create_fuzz_input(self):
        """Test creating FuzzInput"""
        fuzz_input = FuzzInput(
            value="test",
            input_type=InputType.TEXT,
            strategy=FuzzingStrategy.RANDOM,
            metadata={'test': True}
        )

        assert fuzz_input.value == "test"
        assert fuzz_input.input_type == InputType.TEXT
        assert fuzz_input.strategy == FuzzingStrategy.RANDOM
        assert fuzz_input.metadata['test'] == True


class TestFuzzResultDataclass:
    """Test FuzzResult dataclass"""

    def test_create_fuzz_result(self):
        """Test creating FuzzResult"""
        fuzz_input = FuzzInput(
            value="test",
            input_type=InputType.TEXT,
            strategy=FuzzingStrategy.RANDOM
        )

        result = FuzzResult(
            input=fuzz_input,
            success=True,
            error=None,
            crash=False,
            response_time_ms=123.45
        )

        assert result.input == fuzz_input
        assert result.success == True
        assert result.error is None
        assert result.crash == False
        assert result.response_time_ms == 123.45


class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_generate_with_zero_count(self):
        """Test generating with count=0"""
        gen = FuzzGenerator(seed=42)
        inputs = gen.generate(InputType.TEXT, count=0)

        assert len(inputs) == 0

    def test_mutate_with_zero_mutations(self):
        """Test mutation with mutations=0"""
        fuzzer = MutationFuzzer(seed=42)
        mutated = fuzzer.mutate("test", mutations=0)

        assert len(mutated) == 0

    def test_campaign_with_empty_targets(self):
        """Test campaign with no targets"""
        campaign = FuzzingCampaign()
        results = campaign.run_ui_campaign([])

        assert results['total_inputs'] == 0
        assert len(results['targets']) == 0

    def test_campaign_with_empty_endpoints(self):
        """Test campaign with no endpoints"""
        campaign = FuzzingCampaign()
        results = campaign.run_api_campaign([])

        assert results['total_requests'] == 0
        assert len(results['endpoints']) == 0


class TestIntegration:
    """Integration tests for fuzzing module"""

    def test_full_fuzzing_workflow(self):
        """Test complete fuzzing workflow"""
        # Create campaign
        campaign = FuzzingCampaign()

        # Define targets
        ui_targets = [
            {'id': 'username', 'type': 'text_field', 'input_type': 'text'},
            {'id': 'email', 'type': 'text_field', 'input_type': 'email'},
            {'id': 'submit', 'type': 'button'}
        ]

        api_endpoints = [
            {'method': 'POST', 'endpoint': '/api/register', 'param_type': 'email'},
            {'method': 'POST', 'endpoint': '/api/login', 'param_type': 'password'}
        ]

        # Run campaigns
        ui_results = campaign.run_ui_campaign(ui_targets)
        api_results = campaign.run_api_campaign(api_endpoints)

        # Get summary
        summary = campaign.get_summary()

        # Verify results
        assert ui_results['total_inputs'] > 0
        assert api_results['total_requests'] > 0
        assert summary['total_inputs'] > 0
        assert len(summary['campaigns']) == 2

    def test_mutation_and_generation_combined(self):
        """Test combining mutation and generation"""
        gen = FuzzGenerator(seed=42)
        mutator = MutationFuzzer(seed=42)

        # Generate base inputs
        base_inputs = gen.generate(InputType.TEXT, count=5)

        # Mutate them
        mutated_inputs = []
        for base in base_inputs:
            if isinstance(base.value, str):
                mutated = mutator.mutate(base.value, mutations=3)
                mutated_inputs.extend(mutated)

        assert len(mutated_inputs) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
