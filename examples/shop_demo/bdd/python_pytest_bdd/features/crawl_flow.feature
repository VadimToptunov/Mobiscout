Feature: CrawlFlow
  Auto-generated from an autonomous crawl (state + navigation).

  Scenario Outline: The welcome back screen shows its expected controls
    Given the app is launched
    Then "<element>" is visible

    Examples:
      | element |
      | Welcome back |
      | Email |
      | Password |
      | Remember me |
      | Sign in |
      | Forgot password? |

  Scenario: The search products screen shows its expected controls
    Given the app is launched
    When I tap "Sign in"
    Then "Search products" is visible
    And "Search products" is enabled
    And "Running Shoes" is visible
    And "Running Shoes" is enabled
    And "Backpack" is visible
    And "Backpack" is enabled
    And "Cart" is visible
    And "Cart" is enabled

  Scenario: The running shoes screen shows its expected controls
    Given the app is launched
    When I tap "Sign in"
    And I tap "Running Shoes"
    Then "Running Shoes" is visible
    And "Add to cart" is visible
    And "Add to cart" is enabled

  Scenario: The your cart screen shows its expected controls
    Given the app is launched
    When I tap "Sign in"
    And I tap "Cart"
    Then "Your cart" is visible
    And "Place order" is visible
    And "Place order" is enabled

  Scenario: Tapping Sign in opens the search products screen
    Given the app is launched
    When I tap "Sign in"
    Then "Search products" is visible

  Scenario Outline: Multi-step path (4 screens): screen 1 → screen 2 → screen 3 → screen 4
    Given the app is launched
    When I enter "<email>" into "Email"
    And I enter "<password>" into "Password"
    And I tap "Remember me"
    And I tap "Sign in"
    Then "Search products" is visible
    When I enter "<search_products>" into "Search products"
    And I tap "Running Shoes"
    Then "Running Shoes" is visible
    When I tap "Add to cart"
    Then "Your cart" is visible

    Examples:
      | email | password | search_products |
      | test@example.com | Password123! | test |
      | user2@example.com | Secret123! | test 2 |

  Scenario Outline: Multi-step path (3 screens): screen 1 → screen 2 → screen 4
    Given the app is launched
    When I enter "<email>" into "Email"
    And I enter "<password>" into "Password"
    And I tap "Remember me"
    And I tap "Sign in"
    Then "Search products" is visible
    When I enter "<search_products>" into "Search products"
    And I tap "Cart"
    Then "Your cart" is visible

    Examples:
      | email | password | search_products |
      | test@example.com | Password123! | test |
      | user2@example.com | Secret123! | test 2 |

  Scenario Outline: Submitting invalid data on the welcome back form is rejected
    Given the app is launched
    When I enter "<email>" into "Email"
    And I enter "<password>" into "Password"
    And I tap "Sign in"
    Then "Sign in" is visible

    Examples:
      | email | password |
      | not-an-email | 1 |
      | user2@example.com | Secret123! |

