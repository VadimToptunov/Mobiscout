Feature: CrawlFlow
  Auto-generated from an autonomous crawl (state + navigation).

  Scenario: State checks for discovered screen 1
    Given the app is launched
    Then "Welcome back" is visible
    And "Email" is visible
    And "Email" is enabled
    And "Password" is visible
    And "Password" is enabled
    And "Remember me" is visible
    And "Remember me" is enabled
    And "Sign in" is visible
    And "Sign in" is enabled
    And "Forgot password?" is visible
    And "Forgot password?" is enabled

  Scenario: State checks for discovered screen 2
    Given the app is launched
    Then "Search products" is visible
    And "Search products" is enabled
    And "Running Shoes" is visible
    And "Running Shoes" is enabled
    And "Backpack" is visible
    And "Backpack" is enabled
    And "Cart" is visible
    And "Cart" is enabled

  Scenario: State checks for discovered screen 3
    Given the app is launched
    Then "Running Shoes" is visible
    And "$89.00" is visible
    And "Add to cart" is visible
    And "Add to cart" is enabled

  Scenario: State checks for discovered screen 4
    Given the app is launched
    Then "Your cart" is visible
    And "Place order" is visible
    And "Place order" is enabled

  Scenario: Tapping Sign in navigates onward
    Given the app is launched
    When I tap "Sign in"
    Then "Search products" is visible

  Scenario: Multi-step path (4 screens): screen 1 → screen 2 → screen 3 → screen 4
    Given the app is launched
    When I enter "test@example.com" into "Email"
    And I enter "Password123!" into "Password"
    And I tap "Remember me"
    And I tap "Sign in"
    Then "Search products" is visible
    When I enter "test" into "Search products"
    And I tap "Running Shoes"
    Then "Running Shoes" is visible
    When I tap "Add to cart"
    Then "Your cart" is visible

  Scenario: Multi-step path (3 screens): screen 1 → screen 2 → screen 4
    Given the app is launched
    When I enter "test@example.com" into "Email"
    And I enter "Password123!" into "Password"
    And I tap "Remember me"
    And I tap "Sign in"
    Then "Search products" is visible
    When I enter "test" into "Search products"
    And I tap "Cart"
    Then "Your cart" is visible

