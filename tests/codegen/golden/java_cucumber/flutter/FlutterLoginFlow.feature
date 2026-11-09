Feature: FlutterLoginFlow
  Generated Flutter (Route B) login flow used for golden tests.

  Scenario Outline: User can log in with valid credentials
    Given the app is launched
    When I enter "<email_field>" into "email_field"
    And I tap "Log in"
    And I wait 3 seconds
    And I tap "IconButton"
    Then "Welcome" is visible

    Examples:
      | email_field |
      | alice@example.com |

