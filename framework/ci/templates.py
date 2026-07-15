"""
CI/CD Templates - Ready-to-use workflow configurations
"""

# GitHub Actions Templates

GITHUB_BASIC_TEMPLATE = """name: Mobile Tests

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.13'
          
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -e .
          
      - name: Run tests
        run: |
          mobiscout parallel run tests/ --workers 4
          
      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: test-results
          path: reports/
"""

GITHUB_PARALLEL_TEMPLATE = """name: Parallel Mobile Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        shard: [0, 1, 2, 3]  # 4 parallel jobs
        
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.13'
          
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -e .
          
      - name: Create test shards
        run: |
          mobiscout parallel create-shards tests/ 4 --output shards
          
      - name: Run shard ${{ matrix.shard }}
        run: |
          pytest $(cat shards/shard_${{ matrix.shard }}.txt) --junit-xml=reports/junit-${{ matrix.shard }}.xml
          
      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: test-results-shard-${{ matrix.shard }}
          path: reports/
"""

GITHUB_MULTIPLATFORM_TEMPLATE = """name: Multi-Platform Tests

on: [push, pull_request]

jobs:
  test:
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest]
        platform: [android, ios]
        exclude:
          - os: ubuntu-latest
            platform: ios  # iOS requires macOS
        include:
          - os: ubuntu-latest
            platform: android
            emulator: true
          - os: macos-latest
            platform: ios
            simulator: true
    
    runs-on: ${{ matrix.os }}
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.13'
          
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -e .
          
      - name: Set up Android Emulator
        if: matrix.platform == 'android' && matrix.emulator
        uses: reactivecircus/android-emulator-runner@v2
        with:
          api-level: 30
          target: google_apis
          arch: x86_64
          script: mobiscout parallel run tests/android/ --workers 2
          
      - name: Set up iOS Simulator
        if: matrix.platform == 'ios' && matrix.simulator
        run: |
          xcrun simctl boot "iPhone 14"
          mobiscout parallel run tests/ios/ --workers 2
          
      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: test-results-${{ matrix.platform }}
          path: reports/
"""

# GitLab CI Templates

GITLAB_BASIC_TEMPLATE = """stages:
  - test

test:
  stage: test
  image: python:3.13
  
  before_script:
    - pip install -r requirements.txt
    - pip install -e .
    
  script:
    - mobiscout parallel run tests/ --workers 4
    
  artifacts:
    when: always
    paths:
      - reports/
    reports:
      junit: reports/junit.xml
"""

GITLAB_PARALLEL_TEMPLATE = """stages:
  - test

test:
  stage: test
  image: python:3.13
  parallel: 4
  
  before_script:
    - pip install -r requirements.txt
    - pip install -e .
    
  script:
    - mobiscout parallel create-shards tests/ 4 --output shards
    - pytest $(cat shards/shard_${CI_NODE_INDEX}.txt) --junit-xml=reports/junit-${CI_NODE_INDEX}.xml
    
  artifacts:
    when: always
    paths:
      - reports/
    reports:
      junit: reports/junit-*.xml
"""

GITLAB_MULTIPLATFORM_TEMPLATE = """stages:
  - test

.test_template: &test_template
  stage: test
  before_script:
    - pip install -r requirements.txt
    - pip install -e .
  artifacts:
    when: always
    paths:
      - reports/
    reports:
      junit: reports/junit.xml

test:android:
  <<: *test_template
  image: python:3.13
  tags:
    - android
  script:
    - mobiscout parallel run tests/android/ --workers 4

test:ios:
  <<: *test_template
  image: python:3.13
  tags:
    - macos
    - ios
  script:
    - mobiscout parallel run tests/ios/ --workers 4
"""

# Jenkins Templates

JENKINS_BASIC_TEMPLATE = """pipeline {
    agent any
    
    stages {
        stage('Setup') {
            steps {
                sh 'pip install -r requirements.txt'
                sh 'pip install -e .'
            }
        }
        
        stage('Test') {
            steps {
                sh 'mobiscout parallel run tests/ --workers 4'
            }
        }
    }
    
    post {
        always {
            junit 'reports/junit.xml'
            archiveArtifacts artifacts: 'reports/**/*', allowEmptyArchive: true
        }
    }
}
"""

JENKINS_PARALLEL_TEMPLATE = """pipeline {
    agent any
    
    stages {
        stage('Test') {
            parallel {
                stage('Shard 0') {
                    steps {
                        sh 'mobiscout parallel create-shards tests/ 4 --output shards'
                        sh 'pytest $(cat shards/shard_0.txt) --junit-xml=reports/junit-0.xml'
                    }
                }
                stage('Shard 1') {
                    steps {
                        sh 'pytest $(cat shards/shard_1.txt) --junit-xml=reports/junit-1.xml'
                    }
                }
                stage('Shard 2') {
                    steps {
                        sh 'pytest $(cat shards/shard_2.txt) --junit-xml=reports/junit-2.xml'
                    }
                }
                stage('Shard 3') {
                    steps {
                        sh 'pytest $(cat shards/shard_3.txt) --junit-xml=reports/junit-3.xml'
                    }
                }
            }
        }
    }
    
    post {
        always {
            junit 'reports/junit-*.xml'
            archiveArtifacts artifacts: 'reports/**/*', allowEmptyArchive: true
        }
    }
}
"""

# CircleCI Templates

CIRCLECI_BASIC_TEMPLATE = """version: 2.1

jobs:
  test:
    docker:
      - image: python:3.13
    steps:
      - checkout
      - run:
          name: Install dependencies
          command: |
            pip install -r requirements.txt
            pip install -e .
      - run:
          name: Run tests
          command: mobiscout parallel run tests/ --workers 4
      - store_test_results:
          path: reports/
      - store_artifacts:
          path: reports/

workflows:
  test-workflow:
    jobs:
      - test
"""

CIRCLECI_PARALLEL_TEMPLATE = """version: 2.1

jobs:
  test:
    docker:
      - image: python:3.13
    parallelism: 4
    steps:
      - checkout
      - run:
          name: Install dependencies
          command: |
            pip install -r requirements.txt
            pip install -e .
      - run:
          name: Create and run shard
          command: |
            mobiscout parallel create-shards tests/ 4 --output shards
            pytest $(cat shards/shard_${CIRCLE_NODE_INDEX}.txt) --junit-xml=reports/junit-${CIRCLE_NODE_INDEX}.xml
      - store_test_results:
          path: reports/
      - store_artifacts:
          path: reports/

workflows:
  test-workflow:
    jobs:
      - test
"""


def get_template(ci_system: str, template_type: str = "basic") -> str:
    """
    Get CI/CD template by system and type

    Args:
        ci_system: 'github', 'gitlab', 'jenkins', or 'circleci'
        template_type: 'basic', 'parallel', or 'multiplatform'

    Returns:
        Template content as string
    """
    templates = {
        "github": {
            "basic": GITHUB_BASIC_TEMPLATE,
            "parallel": GITHUB_PARALLEL_TEMPLATE,
            "multiplatform": GITHUB_MULTIPLATFORM_TEMPLATE,
        },
        "gitlab": {
            "basic": GITLAB_BASIC_TEMPLATE,
            "parallel": GITLAB_PARALLEL_TEMPLATE,
            "multiplatform": GITLAB_MULTIPLATFORM_TEMPLATE,
        },
        "jenkins": {
            "basic": JENKINS_BASIC_TEMPLATE,
            "parallel": JENKINS_PARALLEL_TEMPLATE,
        },
        "circleci": {
            "basic": CIRCLECI_BASIC_TEMPLATE,
            "parallel": CIRCLECI_PARALLEL_TEMPLATE,
        },
    }

    if ci_system not in templates:
        raise ValueError(f"Unknown CI system: {ci_system}")

    if template_type not in templates[ci_system]:
        raise ValueError(f"Unknown template type '{template_type}' for {ci_system}")

    return templates[ci_system][template_type]


def get_filename(ci_system: str) -> str:
    """Get appropriate filename for CI system"""
    filenames = {
        "github": ".github/workflows/tests.yml",
        "gitlab": ".gitlab-ci.yml",
        "jenkins": "Jenkinsfile",
        "circleci": ".circleci/config.yml",
    }
    return filenames.get(ci_system, "ci-config.yml")
