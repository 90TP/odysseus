package com.seventhhaven.meals

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.MenuBook
import androidx.compose.material.icons.filled.CalendarMonth
import androidx.compose.material.icons.filled.ChatBubbleOutline
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material.icons.filled.ShoppingCart
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import coil.compose.AsyncImage
import com.seventhhaven.meals.data.ApiFactory
import com.seventhhaven.meals.data.AppSettings
import com.seventhhaven.meals.data.RecipeOverview
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import retrofit2.HttpException

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { SeventhHeavenApp() }
    }
}

sealed class Destination(val route: String, val label: String) {
    data object Recipes : Destination("recipes", "Recipes")
    data object Calendar : Destination("calendar", "Calendar")
    data object Aerith : Destination("aerith", "Aerith")
    data object Shopping : Destination("shopping", "Shopping")
    data object Menu : Destination("menu", "Menu")
}

@Composable
fun SeventhHeavenApp() {
    val navController = rememberNavController()
    val destinations = listOf(Destination.Recipes, Destination.Calendar, Destination.Aerith, Destination.Shopping, Destination.Menu)
    Scaffold(bottomBar = { BottomBar(navController, destinations) }) { padding ->
        NavHost(navController = navController, startDestination = Destination.Recipes.route, modifier = Modifier.padding(padding)) {
            composable(Destination.Recipes.route) { RecipesScreen(onOpenRecipe = { id -> navController.navigate("recipe/$id") }) }
            composable("recipe/{id}") { backStackEntry ->
                val id = backStackEntry.arguments?.getString("id")?.toIntOrNull()
                if (id != null) RecipeDetailScreen(id)
            }
            composable(Destination.Calendar.route) { PlaceholderScreen("Calendar") }
            composable(Destination.Aerith.route) { PlaceholderScreen("Aerith") }
            composable(Destination.Shopping.route) { PlaceholderScreen("Shopping") }
            composable(Destination.Menu.route) { SettingsScreen() }
        }
    }
}

@Composable
private fun BottomBar(navController: NavHostController, destinations: List<Destination>) {
    val backStack by navController.currentBackStackEntryAsState()
    val current = backStack?.destination?.route
    NavigationBar {
        destinations.forEach { destination ->
            NavigationBarItem(selected = current == destination.route, onClick = { navController.navigate(destination.route) }, icon = {
                val icon = when (destination) {
                    Destination.Recipes -> Icons.AutoMirrored.Filled.MenuBook
                    Destination.Calendar -> Icons.Filled.CalendarMonth
                    Destination.Aerith -> Icons.Filled.ChatBubbleOutline
                    Destination.Shopping -> Icons.Filled.ShoppingCart
                    Destination.Menu -> Icons.Filled.Menu
                }
                Icon(icon, contentDescription = destination.label)
            }, label = { Text(destination.label) })
        }
    }
}

class RecipeViewModel : ViewModel() {
    var recipes by mutableStateOf<List<RecipeOverview>>(emptyList()); private set
    var loading by mutableStateOf(false); private set
    var error by mutableStateOf<String?>(null); private set

    suspend fun load(factory: ApiFactory, query: String? = null) {
        loading = true; error = null
        try {
            recipes = withContext(Dispatchers.IO) { factory.create().recipes(query = query?.takeIf { it.isNotBlank() }).results }
        } catch (e: HttpException) {
            val body = e.response()?.errorBody()?.string().orEmpty().take(500)
            error = "HTTP ${e.code()}: ${body.ifBlank { e.message() }}"
        } catch (t: Throwable) {
            error = "${t::class.java.simpleName}: ${t.message ?: "Unknown error"}"
        } finally { loading = false }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RecipesScreen(onOpenRecipe: (Int) -> Unit, vm: RecipeViewModel = viewModel()) {
    val context = androidx.compose.ui.platform.LocalContext.current
    val settings = AppSettings(context)
    val factory = ApiFactory(settings)
    val scope = rememberCoroutineScope()
    var query by rememberSaveable { mutableStateOf("") }
    LaunchedEffect(Unit) { vm.load(factory) }
    Scaffold(topBar = { TopAppBar(title = { Text("7th Heaven Meals") }) }) { padding ->
        Column(modifier = Modifier.fillMaxSize().padding(padding).padding(12.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(value = query, onValueChange = { query = it }, modifier = Modifier.weight(1f), label = { Text("Search recipes") })
                Button(onClick = { scope.launch { vm.load(factory, query) } }) { Text("Search") }
            }
            Spacer(Modifier.height(12.dp))
            when {
                vm.loading -> CircularProgressIndicator()
                vm.error != null -> Text("Error: ${vm.error}")
                else -> LazyVerticalGrid(columns = GridCells.Adaptive(160.dp), contentPadding = PaddingValues(bottom = 24.dp), horizontalArrangement = Arrangement.spacedBy(12.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    items(vm.recipes) { recipe -> RecipeCard(recipe, factory, onOpenRecipe) }
                }
            }
        }
    }
}

@Composable
private fun RecipeCard(recipe: RecipeOverview, factory: ApiFactory, onOpenRecipe: (Int) -> Unit) {
    Card(onClick = { onOpenRecipe(recipe.id) }) {
        Column {
            AsyncImage(model = factory.absoluteMediaUrl(recipe.image), contentDescription = recipe.name, modifier = Modifier.fillMaxWidth().height(130.dp), contentScale = ContentScale.Crop)
            Column(Modifier.padding(12.dp)) {
                Text(recipe.name)
                recipe.description?.takeIf { it.isNotBlank() }?.let { Spacer(Modifier.height(4.dp)); Text(it) }
            }
        }
    }
}

@Composable fun RecipeDetailScreen(id: Int) { PlaceholderScreen("Recipe $id") }
@Composable fun PlaceholderScreen(title: String) { Column(modifier = Modifier.fillMaxSize().padding(24.dp)) { Text(title) } }

@Composable
fun SettingsScreen() {
    val context = androidx.compose.ui.platform.LocalContext.current
    val settings = AppSettings(context)
    val scope = rememberCoroutineScope()
    val magicDnsUrl = AppSettings.DEFAULT_BASE_URL
    var token by rememberSaveable { mutableStateOf(settings.authToken) }
    var status by rememberSaveable { mutableStateOf<String?>(null) }
    var testing by rememberSaveable { mutableStateOf(false) }

    // Force the known-good MagicDNS endpoint and overwrite any stale Tailscale-IP preference.
    LaunchedEffect(Unit) { settings.baseUrl = magicDnsUrl }

    Column(modifier = Modifier.fillMaxSize().padding(24.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("Connection")
        OutlinedTextField(value = magicDnsUrl, onValueChange = {}, modifier = Modifier.fillMaxWidth(), readOnly = true, label = { Text("Backend URL (MagicDNS)") })
        OutlinedTextField(value = token, onValueChange = { token = it }, modifier = Modifier.fillMaxWidth(), label = { Text("Tandoor API token") }, supportingText = { Text(if (token.isBlank()) "No token saved" else "Token entered (${token.length} characters)") })
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = { settings.baseUrl = magicDnsUrl; settings.authToken = token; token = settings.authToken; status = "Saved. MagicDNS forced." }) { Text("Save") }
            Button(enabled = !testing, onClick = {
                settings.baseUrl = magicDnsUrl; settings.authToken = token; token = settings.authToken; testing = true; status = "Testing $magicDnsUrl ..."
                scope.launch {
                    val result = withContext(Dispatchers.IO) { ApiFactory(settings).testConnection() }
                    status = result.message; testing = false
                }
            }) { Text(if (testing) "Testing..." else "Test connection") }
        }
        status?.let { Text(it) }
    }
}
