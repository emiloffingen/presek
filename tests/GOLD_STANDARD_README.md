# 🏆 Gold Standard Clustering Dataset

## Overview

This directory contains the gold standard test cases for Presek's clustering algorithm. These test cases serve as the "ground truth" for evaluating clustering quality and preventing regressions in the NLP pipeline.

## Purpose

The gold standard dataset helps ensure that:

1. **Algorithm Quality**: The clustering algorithm produces expected results for known scenarios
2. **Regression Prevention**: Changes to the NLP pipeline don't degrade clustering performance
3. **Edge Case Coverage**: The system handles various edge cases appropriately
4. **Documentation**: Provides clear examples of expected clustering behavior

## Files

### `gold_standard_clustering.json`

The main dataset containing test cases with:

- `title_a`: First article title
- `title_b`: Second article title
- `should_cluster`: Boolean indicating if titles should cluster together
- `reason`: Human-readable explanation of why they should/shouldn't cluster
- `category`: Content category (politics, sports, economy, religion, etc.)
- `expected_behavior`: Detailed description of expected algorithm behavior

### Test Coverage

The dataset currently covers:

✅ **Exact Matches**: Identical titles should always cluster
✅ **Related Stories**: Similar economic/political news should cluster
✅ **Unrelated Content**: Different topics should NOT cluster
✅ **Domain Separation**: Sports vs politics vs religion distinctions
✅ **Edge Cases**: Short titles, special characters, mixed scripts

## Usage

### Running Tests

```bash
# Run all gold standard tests
pytest tests/test_clustering.py::test_gold_standard_* -v

# Run specific gold standard test
pytest tests/test_clustering.py::test_gold_standard_exact_title_match -v
```

### Adding New Test Cases

1. **Identify the scenario**: Find a real-world case where clustering behavior needs validation
2. **Add to JSON**: Follow the existing format in `gold_standard_clustering.json`
3. **Add test function**: Create a new test function in `test_clustering.py` following the pattern
4. **Document**: Update this README if adding new categories or complex scenarios

### Example Test Case

```json
{
  "title_a": "New economic policy announced",
  "title_b": "Government reveals new economic measures",
  "should_cluster": true,
  "entities": ["economic", "policy", "government"],
  "reason": "Same economic policy announcement",
  "category": "economy",
  "expected_behavior": "Related economic news should cluster together"
}
```

## Maintenance

### When to Update

Update the gold standard dataset when:

- ✅ Adding new edge cases discovered in production
- ✅ Algorithm behavior changes intentionally (update expected results)
- ✅ New content domains are added (e.g., technology, health)
- ✅ Regression bugs are fixed (add test case to prevent recurrence)

### Versioning

The dataset includes version metadata. Increment the version when:

- Major changes to test cases
- Significant algorithm updates
- New categories added

## Best Practices

1. **Real-world examples**: Use actual headlines from production when possible
2. **Clear reasoning**: Document why each case should/shouldn't cluster
3. **Category coverage**: Ensure all major content categories are represented
4. **Edge cases**: Include boundary conditions and unusual scenarios
5. **Language consistency**: All test cases should use the same language (Macedonian)

## Integration with CI/CD

The gold standard tests are automatically run in the CI/CD pipeline. If any test fails:

1. **Investigate**: Determine if it's a regression or expected behavior change
2. **Fix**: Either fix the algorithm or update the test case if behavior change is intentional
3. **Document**: Update this README with any significant changes

## Future Enhancements

Potential areas for expansion:

- [ ] Add more sports-related test cases
- [ ] Include international news scenarios
- [ ] Add test cases with entity disambiguation challenges
- [ ] Expand coverage of mixed-language content
- [ ] Add temporal clustering test cases (time-sensitive stories)

## Contact

For questions about the gold standard dataset or clustering algorithm, contact the Presek development team.

---

*Last updated: 2024-05-14* 🚀
