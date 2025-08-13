# Android Client Example

This example demonstrates a minimal Kotlin/Jetpack Compose application that interacts with the FastAPI backend using Retrofit.

## build.gradle (Module)
```kotlin
plugins {
    id("com.android.application")
    kotlin("android")
}

android {
    namespace = "com.example.allotmint"
    compileSdk = 34
    defaultConfig {
        applicationId = "com.example.allotmint"
        minSdk = 24
        targetSdk = 34
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.12.0")
    implementation("androidx.activity:activity-compose:1.8.2")
    implementation("androidx.compose.ui:ui:1.6.0")
    implementation("androidx.compose.material3:material3:1.1.2")

    // Retrofit & JSON
    implementation("com.squareup.retrofit2:retrofit:2.9.0")
    implementation("com.squareup.retrofit2:converter-moshi:2.9.0")
    implementation("com.squareup.okhttp3:logging-interceptor:4.11.0")

    // Coroutines
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.3")
}
```

## Network layer
```kotlin
// models.kt
data class OwnerSummary(
    val owner: String,
    val accounts: List<String>
)

data class Portfolio(
    val owner: String,
    val accounts: Map<String, Any?> // simplify for demo
)

// ApiService.kt
interface ApiService {
    @GET("/owners")
    suspend fun getOwners(): List<OwnerSummary>

    @GET("/portfolio/{owner}")
    suspend fun getPortfolio(@Path("owner") owner: String): Portfolio
}

// RetrofitModule.kt
object RetrofitModule {
    private const val BASE_URL = "https://your-backend-host" // e.g., https://api.example.com

    val api: ApiService by lazy {
        val logger = HttpLoggingInterceptor().apply {
            level = HttpLoggingInterceptor.Level.BODY
        }
        val client = OkHttpClient.Builder()
            .addInterceptor(logger)
            .build()

        Retrofit.Builder()
            .baseUrl(BASE_URL)
            .client(client)
            .addConverterFactory(MoshiConverterFactory.create())
            .build()
            .create(ApiService::class.java)
    }
}
```

## Repository and ViewModel
```kotlin
// Repository.kt
class Repository(private val api: ApiService = RetrofitModule.api) {
    suspend fun owners(): List<OwnerSummary> = api.getOwners()
    suspend fun portfolio(owner: String): Portfolio = api.getPortfolio(owner)
}

// MainViewModel.kt
class MainViewModel(private val repo: Repository = Repository()) : ViewModel() {
    var owners by mutableStateOf<List<OwnerSummary>>(emptyList())
        private set
    var selectedPortfolio by mutableStateOf<Portfolio?>(null)
        private set

    fun loadOwners() {
        viewModelScope.launch {
            owners = repo.owners()
        }
    }

    fun loadPortfolio(owner: String) {
        viewModelScope.launch {
            selectedPortfolio = repo.portfolio(owner)
        }
    }
}
```

## Jetpack Compose UI
```kotlin
// MainScreen.kt
@Composable
fun MainScreen(vm: MainViewModel = viewModel()) {
    LaunchedEffect(Unit) { vm.loadOwners() }

    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        Text("Owners", style = MaterialTheme.typography.titleLarge)
        vm.owners.forEach { owner ->
            Button(onClick = { vm.loadPortfolio(owner.owner) }) {
                Text(owner.owner)
            }
        }
        vm.selectedPortfolio?.let { p ->
            Spacer(Modifier.height(16.dp))
            Text("Portfolio for ${'$'}{p.owner}", style = MaterialTheme.typography.titleMedium)
            // Show accounts here…
        }
    }
}
```

Replace `BASE_URL` with your backend host before running the app.
