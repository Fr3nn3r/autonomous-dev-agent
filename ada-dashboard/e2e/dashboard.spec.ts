import { test, expect, Page } from '@playwright/test';

// Mock API responses
const mockStatus = {
  project_path: '/test/project',
  project_name: 'Test Project',
  is_running: true,
  current_feature_id: 'feat-1',
  current_feature_name: 'Add user authentication',
  current_session_id: 'session-abc123',
  context_usage_percent: 45.5,
  total_sessions: 12,
  features_completed: 3,
  features_total: 8,
  last_updated: new Date().toISOString(),
};

const mockBacklog = {
  project_name: 'Test Project',
  project_path: '/test/project',
  features: [
    {
      id: 'feat-1',
      name: 'Add user authentication',
      description: 'Implement OAuth2 login flow',
      category: 'security',
      status: 'in_progress',
      priority: 1,
      sessions_spent: 2,
      depends_on: [],
      acceptance_criteria: ['Users can log in', 'Users can log out'],
      implementation_notes: [],
      model_override: null,
    },
    {
      id: 'feat-2',
      name: 'Dashboard UI',
      description: 'Create main dashboard interface',
      category: 'ui',
      status: 'completed',
      priority: 2,
      sessions_spent: 1,
      depends_on: [],
      acceptance_criteria: [],
      implementation_notes: [],
      model_override: null,
    },
    {
      id: 'feat-3',
      name: 'API rate limiting',
      description: 'Add rate limiting to API endpoints',
      category: 'backend',
      status: 'pending',
      priority: 3,
      sessions_spent: 0,
      depends_on: ['feat-1'],
      acceptance_criteria: [],
      implementation_notes: [],
      model_override: null,
    },
  ],
  total_features: 3,
  completed_features: 1,
  in_progress_features: 1,
  pending_features: 1,
  blocked_features: 0,
};

const mockCosts = {
  total_cost_usd: 1.2345,
  total_sessions: 12,
  total_input_tokens: 150000,
  total_output_tokens: 45000,
  total_cache_read_tokens: 20000,
  total_cache_write_tokens: 5000,
  cost_by_model: {
    'claude-sonnet-4': 0.85,
    'claude-opus-4': 0.3845,
  },
  sessions_by_model: {
    'claude-sonnet-4': 10,
    'claude-opus-4': 2,
  },
  sessions_by_outcome: {
    success: 8,
    failure: 2,
    handoff: 2,
  },
  period_start: '2025-01-15T00:00:00Z',
  period_end: '2025-01-19T23:59:59Z',
};

const mockProjections = {
  avg_cost_per_feature: 0.41,
  features_remaining: 5,
  features_completed: 3,
  projected_remaining_cost_low: 1.5,
  projected_remaining_cost_mid: 2.05,
  projected_remaining_cost_high: 2.8,
  daily_burn_rate_7d: 0.35,
  estimated_completion_date_mid: '2025-01-25T00:00:00Z',
  total_spent: 1.2345,
  confidence: 'medium' as const,
};

const mockTimeline = {
  features: [
    {
      id: 'feat-2',
      name: 'Dashboard UI',
      status: 'completed',
      started_at: '2025-01-16T10:00:00Z',
      completed_at: '2025-01-16T12:30:00Z',
      sessions: [
        {
          session_id: 'sess-1',
          started_at: '2025-01-16T10:00:00Z',
          ended_at: '2025-01-16T12:30:00Z',
          outcome: 'success',
          cost_usd: 0.25,
        },
      ],
      total_duration_hours: 2.5,
      total_cost_usd: 0.25,
    },
  ],
  earliest_start: '2025-01-16T10:00:00Z',
  latest_end: '2025-01-16T12:30:00Z',
};

const mockAlerts = {
  alerts: [],
  total: 0,
  unread_count: 0,
};

async function setupMocks(page: Page) {
  // Mock all API endpoints
  await page.route('**/api/status', async (route) => {
    await route.fulfill({ json: mockStatus });
  });

  await page.route('**/api/backlog', async (route) => {
    await route.fulfill({ json: mockBacklog });
  });

  await page.route('**/api/sessions/costs*', async (route) => {
    await route.fulfill({ json: mockCosts });
  });

  await page.route('**/api/projections', async (route) => {
    await route.fulfill({ json: mockProjections });
  });

  await page.route('**/api/timeline', async (route) => {
    await route.fulfill({ json: mockTimeline });
  });

  await page.route('**/api/alerts*', async (route) => {
    await route.fulfill({ json: mockAlerts });
  });

  await page.route('**/api/alerts/unread/count', async (route) => {
    await route.fulfill({ json: { count: 0 } });
  });
}

test.describe('ADA Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page);
  });

  test('displays header with title and project name', async ({ page }) => {
    await page.goto('/');

    // Check header elements
    await expect(page.locator('h1')).toContainText('ADA Dashboard');
    await expect(page.locator('header')).toContainText('Test Project');
  });

  test('displays all status cards', async ({ page }) => {
    await page.goto('/');

    // Wait for data to load
    await expect(page.getByText('Running')).toBeVisible();

    // Verify status cards are present
    await expect(page.getByText('Status', { exact: true })).toBeVisible();
    await expect(page.getByText('Features', { exact: true })).toBeVisible();
    await expect(page.getByText('Sessions', { exact: true })).toBeVisible();
    await expect(page.getByText('Total Cost', { exact: true })).toBeVisible();

    // Verify values
    await expect(page.getByText('3 / 8')).toBeVisible(); // Features completed/total
    await expect(page.getByText('12', { exact: true }).first()).toBeVisible(); // Total sessions
    await expect(page.getByText('$1.2345')).toBeVisible(); // Cost
  });

  test('displays current session info when running', async ({ page }) => {
    await page.goto('/');

    // Wait for current session section
    await expect(page.getByText('Current Session')).toBeVisible();

    // Verify current session details - use locator within current session section
    const currentSession = page.locator('text=Current Session').locator('..');
    await expect(currentSession.getByText('Add user authentication')).toBeVisible();
    await expect(page.getByText('session-abc123')).toBeVisible();
    await expect(page.getByText('45.5%')).toBeVisible();
  });

  test('displays feature backlog', async ({ page }) => {
    await page.goto('/');

    // Wait for backlog section
    await expect(page.getByText('Feature Backlog')).toBeVisible();

    // Verify features are displayed - use role to disambiguate
    await expect(page.getByRole('heading', { name: 'Add user authentication' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Dashboard UI' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'API rate limiting' })).toBeVisible();

    // Verify descriptions
    await expect(page.getByText('Implement OAuth2 login flow')).toBeVisible();
  });

  test('displays cost breakdown', async ({ page }) => {
    await page.goto('/');

    // Wait for cost section
    await expect(page.getByText('Cost Breakdown')).toBeVisible();

    // Verify token counts are formatted
    await expect(page.getByText('Input Tokens')).toBeVisible();
    await expect(page.getByText('Output Tokens')).toBeVisible();
    await expect(page.getByText('150.0K')).toBeVisible(); // Input tokens formatted
    await expect(page.getByText('45.0K')).toBeVisible(); // Output tokens formatted

    // Verify model costs
    await expect(page.getByText('By Model')).toBeVisible();
    await expect(page.getByText('claude-sonnet-4')).toBeVisible();

    // Verify outcomes
    await expect(page.getByText('By Outcome')).toBeVisible();
    await expect(page.getByText(/success:\s*8/)).toBeVisible();
  });

  test('shows websocket connection status', async ({ page }) => {
    await page.goto('/');

    // WebSocket won't actually connect in tests (no backend)
    // so it should show Disconnected
    await expect(page.getByText('Disconnected')).toBeVisible();
  });

  test('shows idle status when not running', async ({ page }) => {
    // Override mock for this test
    await page.route('**/api/status', async (route) => {
      await route.fulfill({
        json: {
          ...mockStatus,
          is_running: false,
          current_feature_id: null,
          current_feature_name: null,
          current_session_id: null,
        },
      });
    });

    await page.goto('/');

    await expect(page.getByText('Idle')).toBeVisible();
    // Current session section should not be visible
    await expect(page.getByText('Current Session')).not.toBeVisible();
  });

  test('shows empty state when no features', async ({ page }) => {
    // Override mock for this test
    await page.route('**/api/backlog', async (route) => {
      await route.fulfill({
        json: {
          ...mockBacklog,
          features: [],
          total_features: 0,
        },
      });
    });

    await page.goto('/');

    await expect(page.getByText('No features in backlog')).toBeVisible();
  });

  test('page loads without errors', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));

    await page.goto('/');

    // Wait for initial render
    await expect(page.locator('h1')).toBeVisible();

    // Check no JS errors occurred
    expect(errors).toHaveLength(0);
  });

  test('responsive layout - mobile viewport', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/');

    // Page should still render key elements
    await expect(page.locator('h1')).toContainText('ADA Dashboard');
    await expect(page.getByText('Feature Backlog')).toBeVisible();
    await expect(page.getByText('Cost Breakdown')).toBeVisible();
  });
});

test.describe('Dashboard Components', () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page);
  });

  test('feature cards show correct status icons', async ({ page }) => {
    await page.goto('/');

    // Features should have SVG status icons
    // Wait for backlog to load
    await expect(page.getByText('Feature Backlog')).toBeVisible();

    // Verify feature cards have status indicator SVGs
    // The in-progress feature card contains the feature name and a spinning refresh icon
    const backlogSection = page.locator('.bg-gray-800').filter({ hasText: 'Feature Backlog' });

    // Verify there are SVG icons within the backlog section (status indicators)
    await expect(backlogSection.locator('svg').first()).toBeVisible();
  });

  test('context usage progress bar displays correctly', async ({ page }) => {
    await page.goto('/');

    // Find the progress bar container
    const progressBar = page.locator('[class*="bg-primary-500"]').first();
    await expect(progressBar).toBeVisible();
  });
});
