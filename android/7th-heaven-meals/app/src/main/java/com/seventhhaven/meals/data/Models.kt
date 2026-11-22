package com.seventhhaven.meals.data

import com.squareup.moshi.Json

// Tandoor's exact response shape varies slightly by endpoint/version, so fields are optional
// and intentionally permissive for the first native client.
data class RecipeOverview(
    val id: Int,
    val name: String = "Untitled recipe",
    val description: String? = null,
    val image: String? = null,
    val servings: Int? = null,
    @Json(name = "servings_text") val servingsText: String? = null,
    val keywords: List<Keyword>? = null
)

data class Keyword(
    val id: Int? = null,
    val name: String? = null
)

data class RecipeDetail(
    val id: Int,
    val name: String = "Untitled recipe",
    val description: String? = null,
    val image: String? = null,
    val servings: Int? = null,
    @Json(name = "servings_text") val servingsText: String? = null,
    val steps: List<RecipeStep>? = null,
    val keywords: List<Keyword>? = null
)

data class RecipeStep(
    val id: Int? = null,
    val name: String? = null,
    val instruction: String? = null,
    val ingredients: List<IngredientLine>? = null
)

data class IngredientLine(
    val id: Int? = null,
    val amount: Double? = null,
    val unit: UnitRef? = null,
    val food: FoodRef? = null,
    val note: String? = null
)

data class UnitRef(val name: String? = null)
data class FoodRef(val name: String? = null)

// Some Tandoor versions return a bare array; others wrap pagination.
data class RecipePage(
    val count: Int? = null,
    val next: String? = null,
    val previous: String? = null,
    val results: List<RecipeOverview> = emptyList()
)
