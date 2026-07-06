Feature: CrawlFlow
  Auto-generated from an autonomous crawl (state + navigation).

  Scenario Outline: State checks for discovered screen 1
    Given the app is launched
    Then "<element>" is visible

    Examples:
      | element |
      | Welcome back |
      | Email |
      | Password |
      | Remember me |
      | Sign in |

  Scenario Outline: State checks for discovered screen 2
    Given the app is launched
    Then "<element>" is visible

    Examples:
      | element |
      | Search products |
      | Running Shoes |
      | Backpack |
      | Cart |

  Scenario Outline: State checks for discovered screen 3
    Given the app is launched
    Then "<element>" is visible

    Examples:
      | element |
      | Running Shoes |
      | Add to cart |

  Scenario Outline: State checks for discovered screen 4
    Given the app is launched
    Then "<element>" is visible

    Examples:
      | element |
      | Your cart |
      | Place order |

  Scenario: Tapping Sign in navigates onward
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

