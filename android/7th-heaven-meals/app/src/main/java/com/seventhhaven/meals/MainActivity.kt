package com.seventhhaven.meals

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CalendarMonth
import androidx.compose.material.icons.filled.ChatBubbleOutline
import androidx.compose.material.icons.filled.MenuBook
import androidx.compose.material.icons.filled.Restaurant
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.ShoppingCart
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import coil.compose.AsyncImage
import com.seventhhaven.meals.data.ApiFactory
import com.seventhhaven.meals.data.AppSettings
import com.seventhhaven.meals.data.RecipeDetail
import com.seventhhaven.meals.data.RecipeOverview
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { SeventhHeavenApp() }
    }
}

enum class RootDestination(val route: String, val label: String) {
    Recipes("recipes", "Recipes"),
    Calendar("calendar", "Calendar"),
    Aerith("aerith", "Aerith"),
    Shopping("shopping", "Shopping"),
    Menu("menu", "Menu")
}

@Composable
fun SeventhHeavenApp() {
    val navController = rememberNavController()
    MaterialTheme {
        Scaffold(
            bottomBar = { AppBottomBar(navController) }
        ) { innerPadding ->
            NavHost(
                navController = navController,
                startDestination = RootDestination.Recipes.route,
                modifier = Modifier.padding(innerPadding)
            ) {
                composable(RootDestination.Recipes.route) {
                    RecipesScreen(onOpenRecipe = { id -> navController.navigate("recipe/$id") })
                }
                composable("recipe/{id}") { backStack ->
                    val id = backStack.arguments?.getString("id")?.toIntOrNull()
                    RecipeDetailScreen(id = id, onBack = { navController.popBackStack() })
                }
                composable(RootDestination.Calendar.route) { PlaceholderScreen("Calendar", "Meal planning will live here.") }
                composable(RootDestination.Aerith.route) { PlaceholderScreen("Aerith", "Planner/chat UI will call the existing Aerith backend.") }
                composable(RootDestination.Shopping.route) { PlaceholderScreen("Shopping", "Tandoor shopping-list integration goes here.") }
                composable(RootDestination.Menu.route) { SettingsScreen() }
            }
        }
    }
}

@Composable
private fun AppBottomBar(navController: NavHostController) {
    val backStack by navController.currentBackStackEntryAsState()
    val current = backStack?.destination?.route
    NavigationBar {
        RootDestination.entries.forEach { destination ->
            val icon = when (destination) {
                RootDestination.Recipes -> Icons.Default.Restaurant
                RootDestination.Calendar -> Icons.Default.CalendarMonth
                RootDestination.Aerith -> Icons.Default.ChatBubbleOutline
                RootDestination.Shopping -> Icons.Default.ShoppingCart
                RootDestination.Menu -> Icons.Default.MenuBook
            }
            NavigationBarItem(
                selected = current == destination.route,
                onClick = {
                    navController.navigate(destination.route) {
                        popUpTo(navController.graph.findStartDestination().id) { saveState = true }
                        launchSingleTop = true
                        restoreState = true
                    }
                },
                icon = { Icon(icon, contentDescription = destination.label) },
                label = { Text(destination.label) }
            )
        }
    }
}

class RecipeViewModel : ViewModel() {
    var recipes by mutableStateOf<List<RecipeOverview>>(emptyList())
        private set
    var loading by mutableStateOf(false)
        private set
    var error by mutableStateOf<String?>(null)
        private set

    suspend fun load(factory: ApiFactory, query: String? = null) {
        loading = true
        error = null
        try {
            recipes = withContext(Dispatchers.IO) { factory.create().recipes(query = query).results }
        } catch (t: Throwable) {
            error = t.message ?: t::class.java.simpleName
        } finally {
            loading = false
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RecipesScreen(onOpenRecipe: (Int) -> Unit, vm: RecipeViewModel = viewModel()) {
    val context = LocalContext.current
    val settings = remember { AppSettings(context) }
    val factory = remember(settings.baseUrl, settings.authToken) { ApiFactory(settings) }
    var query by remember { mutableStateOf("") }

    LaunchedEffect(factory) { vm.load(factory) }

    Column(Modifier.fillMaxSize()) {
        TopAppBar(title = { Text("7th Heaven Meals") })
        OutlinedTextField(
            value = query,
            onValueChange = { query = it },
            label = { Text("Search recipes") },
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
            singleLine = true,
            trailingIcon = {
                Button(onClick = { /* Launched from key-less simple UI below */ }) { Text("Go") }
            }
        )
        when {
            vm.loading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
            vm.error != null -> ErrorCard(vm.error ?: "Unknown error") { /* settings via Menu */ }
            vm.recipes.isEmpty() -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { Text("No recipes found") }
            else -> LazyVerticalGrid(
                columns = GridCells.Adaptive(160.dp),
                contentPadding = PaddingValues(12.dp),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                items(vm.recipes, key = { it.id }) { recipe ->
                    RecipeCard(recipe, factory.absoluteMediaUrl(recipe.image)) { onOpenRecipe(recipe.id) }
                }
            }
        }
    }
}

@Composable
private fun RecipeCard(recipe: RecipeOverview, imageUrl: String?, onClick: () -> Unit) {
    Card(modifier = Modifier.fillMaxWidth().clickable(onClick = onClick)) {
        Column {
            AsyncImage(
                model = imageUrl,
                contentDescription = recipe.name,
                modifier = Modifier.fillMaxWidth().height(130.dp).background(MaterialTheme.colorScheme.surfaceVariant),
                contentScale = ContentScale.Crop
            )
            Column(Modifier.padding(12.dp)) {
                Text(recipe.name, fontWeight = FontWeight.SemiBold)
                recipe.description?.takeIf { it.isNotBlank() }?.let {
                    Spacer(Modifier.height(4.dp))
                    Text(it, style = MaterialTheme.typography.bodySmall, maxLines = 2)
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RecipeDetailScreen(id: Int?, onBack: () -> Unit) {
    val context = LocalContext.current
    val settings = remember { AppSettings(context) }
    val factory = remember { ApiFactory(settings) }
    var recipe by remember { mutableStateOf<RecipeDetail?>(null) }
    var error by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(id) {
        if (id == null) {
            error = "Invalid recipe id"
        } else {
            try {
                recipe = withContext(Dispatchers.IO) { factory.create().recipe(id) }
            } catch (t: Throwable) {
                error = t.message
            }
        }
    }

    Column(Modifier.fillMaxSize()) {
        TopAppBar(
            title = { Text(recipe?.name ?: "Recipe") },
            navigationIcon = { Button(onClick = onBack) { Text("Back") } }
        )
        when {
            error != null -> ErrorCard(error ?: "Error", onBack)
            recipe == null -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
            else -> LazyColumn(contentPadding = PaddingValues(bottom = 32.dp)) {
                item {
                    AsyncImage(
                        model = factory.absoluteMediaUrl(recipe!!.image),
                        contentDescription = recipe!!.name,
                        modifier = Modifier.fillMaxWidth().height(260.dp),
                        contentScale = ContentScale.Crop
                    )
                    Column(Modifier.padding(16.dp)) {
                        recipe!!.description?.takeIf { it.isNotBlank() }?.let { Text(it) }
                        recipe!!.servings?.let { Text("Servings: $it", modifier = Modifier.padding(top = 8.dp)) }
                    }
                }
                recipe!!.steps.orEmpty().forEachIndexed { index, step ->
                    item {
                        Column(Modifier.padding(horizontal = 16.dp, vertical = 10.dp)) {
                            Text(step.name?.takeIf { it.isNotBlank() } ?: "Step ${index + 1}", fontWeight = FontWeight.Bold)
                            if (!step.ingredients.isNullOrEmpty()) {
                                Spacer(Modifier.height(6.dp))
                                step.ingredients.forEach { ingredient ->
                                    val amount = ingredient.amount?.let { if (it % 1.0 == 0.0) it.toInt().toString() else it.toString() }.orEmpty()
                                    val unit = ingredient.unit?.name.orEmpty()
                                    val food = ingredient.food?.name.orEmpty()
                                    val note = ingredient.note.orEmpty()
                                    Text("• ${listOf(amount, unit, food, note).filter { it.isNotBlank() }.joinToString(" ")}")
                                }
                            }
                            step.instruction?.takeIf { it.isNotBlank() }?.let {
                                Spacer(Modifier.height(8.dp))
                                Text(it)
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun PlaceholderScreen(title: String, body: String) {
    Box(Modifier.fillMaxSize().padding(24.dp), contentAlignment = Alignment.Center) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text(title, style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(12.dp))
            Text(body)
        }
    }
}

@Composable
private fun ErrorCard(message: String, action: () -> Unit) {
    Box(Modifier.fillMaxSize().padding(24.dp), contentAlignment = Alignment.Center) {
        Card {
            Column(Modifier.padding(20.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                Text("Couldn’t load data", fontWeight = FontWeight.Bold)
                Spacer(Modifier.height(8.dp))
                Text(message)
                Spacer(Modifier.height(12.dp))
                Button(onClick = action) { Text("OK") }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen() {
    val context = LocalContext.current
    val settings = remember { AppSettings(context) }
    var baseUrl by remember { mutableStateOf(settings.baseUrl) }
    var token by remember { mutableStateOf(settings.authToken) }
    var saved by remember { mutableStateOf(false) }

    Column(Modifier.fillMaxSize()) {
        TopAppBar(title = { Text("Menu & Settings") })
        Column(Modifier.padding(16.dp)) {
            Text("Backend", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(8.dp))
            OutlinedTextField(
                value = baseUrl,
                onValueChange = { baseUrl = it; saved = false },
                label = { Text("7th Heaven / Tandoor URL") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true
            )
            Spacer(Modifier.height(12.dp))
            OutlinedTextField(
                value = token,
                onValueChange = { token = it; saved = false },
                label = { Text("API token (optional)") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true
            )
            Spacer(Modifier.height(16.dp))
            Button(onClick = {
                settings.baseUrl = baseUrl
                settings.authToken = token
                saved = true
            }) {
                Icon(Icons.Default.Settings, contentDescription = null)
                Spacer(Modifier.width(8.dp))
                Text("Save")
            }
            if (saved) {
                Spacer(Modifier.height(8.dp))
                Text("Saved. Return to Recipes to reconnect.")
            }
        }
    }
}
