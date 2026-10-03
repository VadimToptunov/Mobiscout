import SwiftUI

@main
struct ShopApp: App {
    var body: some Scene {
        WindowGroup {
            HomeView()
        }
    }
}

struct HomeView: View {
    @State private var showSettings = false
    var body: some View {
        NavigationStack {
            VStack {
                Text("Welcome").accessibilityIdentifier("home_title")
                NavigationLink(destination: DetailsView()) {
                    Text("Details")
                }
                .accessibilityIdentifier("open_details")
                NavigationLink("Profile", destination: ProfileView())
                NavigationLink {
                    OrdersView()
                } label: {
                    Text("Orders")
                }
                Button("Settings") { showSettings = true }
            }
            .sheet(isPresented: $showSettings) { SettingsView() }
        }
    }
}

struct DetailsView: View {
    var body: some View { Text("Item details").accessibilityIdentifier("details_title") }
}
struct ProfileView: View {
    var body: some View { Text("Your profile").accessibilityIdentifier("profile_title") }
}
struct OrdersView: View {
    var body: some View { Text("Your orders").accessibilityIdentifier("orders_title") }
}
struct SettingsView: View {
    var body: some View { Text("Preferences").accessibilityIdentifier("settings_title") }
}
