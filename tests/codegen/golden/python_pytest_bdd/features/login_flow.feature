Feature: LoginFlow
  Generated login flow used for golden tests.

  Scenario: User can log in with valid credentials
    Given the app is launched
    When I enter "alice@example.com" into "user_field"
    And I tap "login_btn"
    And I wait 3 seconds
    And I press back
    Then "Welcome" is visible

