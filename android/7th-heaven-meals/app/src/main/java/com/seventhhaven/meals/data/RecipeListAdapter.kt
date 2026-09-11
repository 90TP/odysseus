package com.seventhhaven.meals.data

import com.squareup.moshi.FromJson
import com.squareup.moshi.JsonReader

class RecipeListAdapter {
    @FromJson
    fun fromJson(reader: JsonReader): RecipePage {
        return when (reader.peek()) {
            JsonReader.Token.BEGIN_ARRAY -> {
                val items = mutableListOf<RecipeOverview>()
                reader.beginArray()
                while (reader.hasNext()) {
                    items += readOverview(reader)
                }
                reader.endArray()
                RecipePage(count = items.size, results = items)
            }
            JsonReader.Token.BEGIN_OBJECT -> {
                var count: Int? = null
                var next: String? = null
                var previous: String? = null
                var results: List<RecipeOverview> = emptyList()
                reader.beginObject()
                while (reader.hasNext()) {
                    when (reader.nextName()) {
                        "count" -> count = if (reader.peek() == JsonReader.Token.NULL) { reader.nextNull<Unit>(); null } else reader.nextInt()
                        "next" -> next = readNullableString(reader)
                        "previous" -> previous = readNullableString(reader)
                        "results" -> {
                            val list = mutableListOf<RecipeOverview>()
                            reader.beginArray()
                            while (reader.hasNext()) list += readOverview(reader)
                            reader.endArray()
                            results = list
                        }
                        else -> reader.skipValue()
                    }
                }
                reader.endObject()
                RecipePage(count = count, next = next, previous = previous, results = results)
            }
            else -> throw IllegalStateException("Unexpected recipe response: ${reader.peek()}")
        }
    }

    private fun readOverview(reader: JsonReader): RecipeOverview {
        var id = 0
        var name = "Untitled recipe"
        var description: String? = null
        var image: String? = null
        var servings: Int? = null
        var servingsText: String? = null
        reader.beginObject()
        while (reader.hasNext()) {
            when (reader.nextName()) {
                "id" -> id = reader.nextInt()
                "name" -> name = readNullableString(reader) ?: name
                "description" -> description = readNullableString(reader)
                "image" -> image = readNullableString(reader)
                "servings" -> servings = if (reader.peek() == JsonReader.Token.NULL) { reader.nextNull<Unit>(); null } else reader.nextInt()
                "servings_text" -> servingsText = readNullableString(reader)
                else -> reader.skipValue()
            }
        }
        reader.endObject()
        return RecipeOverview(id = id, name = name, description = description, image = image, servings = servings, servingsText = servingsText)
    }

    private fun readNullableString(reader: JsonReader): String? {
        return if (reader.peek() == JsonReader.Token.NULL) {
            reader.nextNull<Unit>()
            null
        } else reader.nextString()
    }
}
