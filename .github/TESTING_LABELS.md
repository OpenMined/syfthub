# Testing the Issue Labeling System

This document provides guidance on testing the automated issue labeling system.

## Testing the Label Setup Workflow

The label setup workflow creates all labels in the repository. To test it:

1. Go to the repository on GitHub
2. Navigate to **Actions** → **Setup Repository Labels**
3. Click **Run workflow** → **Run workflow**
4. Wait for the workflow to complete
5. Navigate to **Issues** → **Labels** to verify all labels were created

Expected labels to be created:
- 9 area labels (blue)
- 6 type labels (various colors)
- 3 priority labels
- 4 status labels
- 2 community labels
- 5 special labels

## Testing the Automatic Labeling Workflow

The automatic labeling workflow runs whenever an issue is opened or edited. To test it:

### Test Case 1: Backend Bug

Create an issue with:
- **Title**: "Bug in FastAPI endpoint"
- **Body**: "The backend API is returning 500 errors when..."

**Expected labels**: `type: bug`, `area: backend`

### Test Case 2: Frontend Feature Request

Create an issue with:
- **Title**: "Add dark mode to React UI"
- **Body**: "It would be great if the frontend supported dark mode..."

**Expected labels**: `type: enhancement`, `area: frontend`

### Test Case 3: Security Issue

Create an issue with:
- **Title**: "Security vulnerability in authentication"
- **Body**: "I found a security issue in the JWT token validation..."

**Expected labels**: `type: bug`, `area: auth`, `security`, `priority: high`

### Test Case 4: SDK Question

Create an issue with:
- **Title**: "How to use the Python SDK for authentication?"
- **Body**: "I'm trying to use the syfthub-sdk to authenticate..."

**Expected labels**: `type: question`, `area: sdk`, `area: auth`

### Test Case 5: Documentation Enhancement

Create an issue with:
- **Title**: "Improve documentation for deployment"
- **Body**: "The docs for Docker deployment could be more detailed..."

**Expected labels**: `type: enhancement`, `area: documentation`, `area: devops`

### Test Case 6: Database Performance Issue

Create an issue with:
- **Title**: "PostgreSQL queries are slow"
- **Body**: "The database performance is degrading with large datasets..."

**Expected labels**: `type: performance`, `area: database`

### Test Case 7: Multi-component Issue

Create an issue with:
- **Title**: "Integration issue between frontend and backend"
- **Body**: "The React frontend can't communicate with the FastAPI backend..."

**Expected labels**: `type: bug`, `area: frontend`, `area: backend`

### Test Case 8: Good First Issue

Create an issue with:
- **Title**: "Add unit tests for user model"
- **Body**: "This is a good first issue for new contributors. We need to add tests..."

**Expected labels**: `type: testing`, `good first issue`

## Testing Issue Templates

Test that issue templates work correctly:

### Test Bug Report Template

1. Go to **Issues** → **New issue**
2. Select **Bug Report**
3. Fill out the form with test data
4. Submit the issue
5. Verify that `type: bug` and `status: needs-triage` labels are automatically applied

### Test Feature Request Template

1. Go to **Issues** → **New issue**
2. Select **Feature Request**
3. Fill out the form with test data
4. Submit the issue
5. Verify that `type: enhancement` and `status: needs-triage` labels are automatically applied

### Test Question Template

1. Go to **Issues** → **New issue**
2. Select **Question or Support**
3. Fill out the form with test data
4. Submit the issue
5. Verify that `type: question` and `status: needs-triage` labels are automatically applied

## Testing Welcome Messages

To test the welcome message for first-time contributors:

1. Create a test GitHub account (or use an account that hasn't opened issues in this repo)
2. Open an issue with this account
3. Verify that a welcome comment is automatically posted

## Manual Testing Checklist

After deploying the labeling system, verify:

- [ ] All labels exist in the repository with correct colors and descriptions
- [ ] The label-issues workflow runs on issue creation
- [ ] The label-issues workflow runs on issue edits
- [ ] Labels are correctly applied based on content
- [ ] Multiple labels can be applied to a single issue
- [ ] Issue templates appear in the "New issue" dropdown
- [ ] Issue templates have the correct initial labels
- [ ] Welcome messages are sent to first-time contributors
- [ ] The workflow handles edge cases (empty body, special characters, etc.)

## Troubleshooting

### Labels Not Applied

If labels aren't being applied automatically:

1. Check the workflow run in the **Actions** tab
2. Look for errors in the workflow logs
3. Verify that the repository has the `issues: write` permission for workflows
4. Check that the labels exist in the repository

### Workflow Not Triggering

If the workflow doesn't run:

1. Verify the workflow file is in `.github/workflows/` 
2. Check that the workflow has proper permissions
3. Ensure the workflow is enabled in repository settings
4. Look for YAML syntax errors in the workflow file

### Incorrect Labels

If wrong labels are applied:

1. Review the labeling logic in `label-issues.yml`
2. Check for keyword conflicts or ambiguities
3. Update the workflow to improve detection logic
4. Test with representative issue titles and bodies

## Monitoring

After deployment, maintainers should:

1. Monitor workflow runs for failures
2. Review automatically labeled issues for accuracy
3. Collect feedback from contributors
4. Adjust labeling logic based on patterns
5. Update documentation based on common questions

## Continuous Improvement

To improve the labeling system over time:

1. Track which labels are most commonly misapplied
2. Identify new patterns in issue content
3. Add new labels as the project evolves
4. Refine keyword detection logic
5. Gather feedback from maintainers and contributors
6. Update issue templates based on common missing information

## Example Testing Script

Here's a simple script to test multiple scenarios:

```bash
#!/bin/bash
# This is a manual testing guide, not an automated script

# Test 1: Backend bug
echo "Create issue: 'Bug in FastAPI endpoint returning 500 errors'"

# Test 2: Frontend feature
echo "Create issue: 'Add dark mode support to React UI'"

# Test 3: Security issue
echo "Create issue: 'Security vulnerability in JWT token validation'"

# Test 4: SDK question
echo "Create issue: 'How to use Python SDK authentication?'"

# Test 5: Multi-area
echo "Create issue: 'Frontend can't connect to backend API'"
```

Run through each test case manually and verify the expected labels are applied.
