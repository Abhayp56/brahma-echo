package com.brahma.connect.contacts

import android.content.Context
import android.database.Cursor
import android.provider.ContactsContract
import android.util.Log

object ContactsHelper {
    private const val TAG = "ContactsHelper"

    /**
     * Reads all device contacts with phone numbers.
     * Returns a list of maps containing 'name' and 'phone'.
     */
    fun fetchContacts(context: Context): List<Map<String, String>> {
        val contactsList = mutableListOf<Map<String, String>>()
        val seenNumbers = mutableSetOf<String>()

        val projection = arrayOf(
            ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME,
            ContactsContract.CommonDataKinds.Phone.NUMBER
        )

        try {
            val cursor: Cursor? = context.contentResolver.query(
                ContactsContract.CommonDataKinds.Phone.CONTENT_URI,
                projection,
                null,
                null,
                ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME + " ASC"
            )

            cursor?.use {
                val nameIndex = it.getColumnIndex(ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME)
                val numberIndex = it.getColumnIndex(ContactsContract.CommonDataKinds.Phone.NUMBER)

                while (it.moveToNext()) {
                    val name = if (nameIndex != -1) it.getString(nameIndex)?.trim().orEmpty() else ""
                    val number = if (numberIndex != -1) it.getString(numberIndex)?.trim().orEmpty() else ""

                    val cleanNumber = number.replace(Regex("[^0-9+]"), "")
                    if (cleanNumber.length >= 7 && cleanNumber !in seenNumbers) {
                        seenNumbers.add(cleanNumber)
                        contactsList.add(
                            mapOf(
                                "name" to (if (name.isNotBlank()) name else cleanNumber),
                                "phone" to cleanNumber
                            )
                        )
                    }
                }
            }
            Log.i(TAG, "Successfully read ${contactsList.size} contacts from device.")
        } catch (e: Exception) {
            Log.e(TAG, "Failed reading device contacts: ${e.message}", e)
        }

        return contactsList
    }
}
