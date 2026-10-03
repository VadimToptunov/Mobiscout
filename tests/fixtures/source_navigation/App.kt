class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        setContent { AppNavHost() }
    }
}

@Composable
fun AppNavHost() {
    val navController = rememberNavController()
    NavHost(navController, startDestination = "home") {
        composable("home") { HomeScreen(navController) }
        composable("details") { DetailsScreen() }
        composable("settings") { SettingsScreen() }
    }
}

@Composable
fun HomeScreen(navController: NavController) {
    Column {
        Text("Welcome", modifier = Modifier.testTag("home_title"))
        Button(onClick = { navController.navigate("details") }, modifier = Modifier.testTag("open_details")) {
            Text("Details")
        }
        Text("Settings", modifier = Modifier.clickable { navController.navigate("settings") })
    }
}

@Composable
fun DetailsScreen() {
    Text("Item details", modifier = Modifier.testTag("details_title"))
}

@Composable
fun SettingsScreen() {
    Text("Preferences", modifier = Modifier.testTag("settings_title"))
}
